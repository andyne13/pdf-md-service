import asyncio
import logging
import time

import pypdfium2
import ray
from ray import serve

from core.markdown_injector import inject_captions

logger = logging.getLogger("ray.serve")


@serve.deployment(
    ray_actor_options={"num_gpus": 0},
    autoscaling_config={
        "min_replicas": 1,
        "max_replicas": 3,
        "target_num_ongoing_requests_per_replica": 5,
    },
    max_ongoing_requests=20,
)
class Dispatcher:
    def __init__(
        self,
        vlm_base_url: str,
        vlm_api_key: str,
        vlm_model: str,
        caption_prompt: str,
        chunk_size: int = 10,
        pool_workers: int = 4,
    ):
        from core.captioning.vlm_captioner import VlmCaptioner
        from core.retry.exponential_backoff import ExponentialBackoffRetry
        from services.webhook_sender import HttpWebhookSender
        from services.worker import MarkerWorkerActor

        self.worker = MarkerWorkerActor.options(
            name="MarkerWorkerActor",
            namespace="serve",
            lifetime="detached",
            num_gpus=0.01,
        ).remote(pool_workers)
        ray.get(self.worker.__ray_ready__.remote())

        self.chunk_size = chunk_size

        caption_retry = ExponentialBackoffRetry(
            max_retries=6, base_delay=0.5, max_delay=12.0, jitter=0.3,
        )
        self.captioner = VlmCaptioner(
            base_url=vlm_base_url,
            api_key=vlm_api_key,
            model=vlm_model,
            retry_policy=caption_retry,
        )

        webhook_retry = ExponentialBackoffRetry(
            max_retries=10, base_delay=1.0, max_delay=30.0, jitter=0.4,
        )
        self.webhook_sender = HttpWebhookSender(webhook_retry)
        self.caption_prompt = caption_prompt
        self._vlm_semaphore = asyncio.Semaphore(8)

        logger.info("Dispatcher initialized (chunk_size=%d)", chunk_size)

    async def __call__(self, request):
        form = await request.form()
        webhook_url = form["webhook_url"]

        caption_str = (form.get("caption") or "true").strip().lower()
        caption_enabled = caption_str not in ("false", "0", "no")

        pdf_files = form.getlist("files")
        filenames = []
        pdf_bytes_list = []
        for f in pdf_files:
            filenames.append(f.filename or f"file_{len(filenames)}")
            pdf_bytes_list.append(await f.read())

        logger.info("Batch received: %d PDFs (caption=%s)", len(pdf_bytes_list), caption_enabled)
        asyncio.get_event_loop().create_task(
            self._process_batch(pdf_bytes_list, filenames, webhook_url, caption_enabled)
        )

        return {"status": "queued", "files_received": len(pdf_bytes_list)}

    @staticmethod
    def _get_page_count(pdf_bytes: bytes) -> int:
        pdf = pypdfium2.PdfDocument(pdf_bytes)
        count = len(pdf)
        pdf.close()
        return count

    @staticmethod
    def _create_chunks(page_count: int, chunk_size: int) -> list[tuple[list[int], str]]:
        if page_count <= chunk_size:
            return [(list(range(page_count)), f"({page_count}p)")]
        chunks = []
        for start in range(0, page_count, chunk_size):
            end = min(start + chunk_size, page_count)
            page_range = list(range(start, end))
            label = f"[p{start}-{end - 1}]"
            chunks.append((page_range, label))
        return chunks

    async def _caption_images(self, images: list[dict]) -> list[str]:
        async def _guarded_caption(img_bytes):
            async with self._vlm_semaphore:
                return await self.captioner.caption(img_bytes, self.caption_prompt)

        captions = await asyncio.gather(
            *[_guarded_caption(img["bytes"]) for img in images],
            return_exceptions=True,
        )
        clean_captions = []
        for c in captions:
            if isinstance(c, Exception):
                logger.error("Caption failed: %s", c)
                clean_captions.append("")
            else:
                clean_captions.append(c)
        return clean_captions

    async def _convert_and_caption(self, idx, pdf_ref, pdf_bytes, filename, caption_enabled=True, webhook_url=None):
        """Convert a single PDF with per-chunk Ray calls using object ref."""
        t0 = time.time()

        page_count = self._get_page_count(pdf_bytes)
        size_mb = len(pdf_bytes) / (1024 * 1024)
        chunks = self._create_chunks(page_count, self.chunk_size)

        logger.info(
            "%s (%d pages, %.1fMB) -> %d chunk(s)",
            filename, page_count, size_mb, len(chunks),
        )

        # Per-chunk Ray calls with object ref (tiny payload per call)
        async def _convert_chunk(page_range, label):
            try:
                return await self.worker.convert_pdf.remote(pdf_ref, page_range)
            except Exception as e:
                logger.error("  [FAIL] %s %s: %s", filename, label, e)
                return None

        chunk_results = await asyncio.gather(
            *[_convert_chunk(pr, label) for pr, label in chunks]
        )

        convert_time = time.time() - t0
        parts = []
        all_chunk_images = []
        for result, (_, label) in zip(chunk_results, chunks):
            if result is None:
                all_chunk_images.append([])
                continue
            md = result.get("markdown", "")
            images = result.get("images", [])
            if md:
                parts.append(md)
            all_chunk_images.append(images)
            logger.info(
                "  [CONVERTED] %-45s (%d chars, %d images)",
                f"{filename} {label}", len(md), len(images),
            )

        if not parts:
            logger.info("%s conversion failed (all chunks empty)", filename)
            return None

        raw_markdown = "\n\n".join(parts)
        total_images = sum(len(imgs) for imgs in all_chunk_images)
        logger.info(
            "%s converted in %.1fs (%d chars, %d images)",
            filename, convert_time, len(raw_markdown), total_images,
        )

        # Send "converted" webhook with raw markdown
        if webhook_url:
            try:
                await self.webhook_sender.send(webhook_url, {
                    "status": "converted",
                    "index": idx,
                    "filename": filename,
                    "result": raw_markdown,
                })
            except Exception:
                logger.warning("Failed to send converted webhook for %s", filename)

        if not caption_enabled or total_images == 0:
            return raw_markdown

        # Phase 2: Caption images for each chunk
        t_cap = time.time()
        captioned_parts = []
        for result, chunk_images in zip(chunk_results, all_chunk_images):
            if result is None:
                continue
            md = result.get("markdown", "")
            if not md:
                continue
            if chunk_images:
                captions = await self._caption_images(chunk_images)
                md = inject_captions(md, chunk_images, captions)
            captioned_parts.append(md)

        caption_time = time.time() - t_cap
        total_time = time.time() - t0
        captioned_markdown = "\n\n".join(captioned_parts)

        logger.info(
            "%s captioned in %.1fs (total %.1fs, %d chars, %d images)",
            filename, caption_time, total_time, len(captioned_markdown), total_images,
        )

        return captioned_markdown

    async def _process_batch(self, pdf_bytes_list, filenames, webhook_url, caption_enabled=True):
        batch_start = time.time()

        # Sort by size descending (largest first) for optimal pool scheduling
        sorted_indices = sorted(
            range(len(pdf_bytes_list)),
            key=lambda i: len(pdf_bytes_list[i]),
            reverse=True,
        )

        # Log chunk plan (in processing order)
        all_chunks = []
        for i in sorted_indices:
            pdf_bytes = pdf_bytes_list[i]
            filename = filenames[i]
            page_count = self._get_page_count(pdf_bytes)
            chunks = self._create_chunks(page_count, self.chunk_size)
            for page_range, label in chunks:
                all_chunks.append(f"  {filename} {label} ({len(page_range)} pages)")

        lines = [
            "",
            "=" * 60,
            f"BATCH: {len(pdf_bytes_list)} PDFs -> {len(all_chunks)} chunks (chunk_size={self.chunk_size})",
            "=" * 60,
        ]
        for c in all_chunks:
            lines.append(c)
        lines.append("")
        logger.info("\n".join(lines))

        try:
            total = len(pdf_bytes_list)
            final_results = [None] * total
            completed = 0

            # Store PDF bytes in Ray object store once per PDF
            pdf_refs = {}
            for i in sorted_indices:
                pdf_refs[i] = ray.put(pdf_bytes_list[i])

            async def _process_one(i, pdf_ref, pdf_bytes, filename):
                nonlocal completed
                try:
                    result = await self._convert_and_caption(
                        i, pdf_ref, pdf_bytes, filename, caption_enabled, webhook_url,
                    )
                except Exception:
                    logger.exception("Processing failed for %s", filename)
                    result = None
                final_results[i] = result
                completed += 1
                try:
                    await self.webhook_sender.send(
                        webhook_url,
                        {
                            "status": "progress",
                            "index": i,
                            "filename": filename,
                            "completed": completed,
                            "total": total,
                            "result": result,
                        },
                    )
                except Exception:
                    logger.warning("Failed to send progress webhook for PDF %d", i)
                return result

            # Stagger submissions: largest PDFs first so their chunks enter pool first
            tasks = []
            for i in sorted_indices:
                task = asyncio.create_task(
                    _process_one(i, pdf_refs[i], pdf_bytes_list[i], filenames[i])
                )
                tasks.append(task)
                await asyncio.sleep(0.05)

            await asyncio.gather(*tasks, return_exceptions=True)

            batch_time = time.time() - batch_start
            succeeded = sum(1 for r in final_results if r is not None)
            logger.info(
                "\nBatch done in %.1fs (%d/%d succeeded)",
                batch_time, succeeded, total,
            )

            await self.webhook_sender.send(
                webhook_url,
                {
                    "status": "finished",
                    "count": total,
                    "results": final_results,
                },
            )
        except Exception:
            logger.exception("Batch processing failed")
            try:
                await self.webhook_sender.send(
                    webhook_url,
                    {"status": "error", "error": "Batch processing failed"},
                )
            except Exception:
                logger.exception("Failed to send error webhook")
