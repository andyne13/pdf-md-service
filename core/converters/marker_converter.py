import gc
import io
import logging
import tempfile
from pathlib import Path
from typing import Dict, List

import torch
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.output import text_from_rendered

from core.interfaces import Converter

logger = logging.getLogger("pdf_md_service")


class MarkerPdfConverter(Converter):
    def __init__(self, max_processes: int = 2, max_tasks_per_child: int = 10):
        import torch.multiprocessing as mp
        from concurrent.futures import ProcessPoolExecutor

        self.converter_config = {
            "output_format": "markdown",
            "disable_multiprocessing": False,
            "pdftext_workers": 2,
        }

        self.model_dict = create_model_dict()
        for v in self.model_dict.values():
            if hasattr(v, "model") and hasattr(v.model, "share_memory"):
                v.model.share_memory()

        try:
            if mp.get_start_method(allow_none=True) != "spawn":
                mp.set_start_method("spawn", force=True)
        except RuntimeError:
            pass

        executor_kwargs = {
            "max_workers": max_processes,
            "initializer": _worker_init,
            "initargs": (self.model_dict,),
            "mp_context": mp.get_context("spawn"),
        }
        # max_tasks_per_child requires Python 3.11+
        import sys
        if sys.version_info >= (3, 11):
            executor_kwargs["max_tasks_per_child"] = max_tasks_per_child
        self.executor = ProcessPoolExecutor(**executor_kwargs)
        self._max_processes = max_processes
        logger.info("MarkerPdfConverter initialized with %d worker processes", max_processes)

    @staticmethod
    def _process_pdf(pdf_path: str, config: dict) -> Dict:
        global _worker_model_dict
        import os
        import time as _time

        pid = os.getpid()
        page_range = config.get("page_range")
        if page_range is not None:
            label = f"[p{page_range[0]}-{page_range[-1]}]"
        else:
            label = "(all pages)"
        print(f"[POOL-WORKER pid={pid}] START {label}", flush=True)
        t0 = _time.time()

        try:
            converter = PdfConverter(
                artifact_dict=_worker_model_dict,
                config=config,
            )
            rendered = converter(pdf_path)
            text, _, images = text_from_rendered(rendered)

            image_list: List[Dict] = []
            for name, img in images.items():
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                image_list.append({"path": name, "bytes": buf.getvalue()})

            elapsed = _time.time() - t0
            print(
                f"[POOL-WORKER pid={pid}] DONE  {label} in {elapsed:.1f}s"
                f" ({len(text)} chars, {len(image_list)} images)",
                flush=True,
            )
            return {"markdown": text, "images": image_list}
        finally:
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()

    def convert(self, pdf_bytes: bytes, page_range: list[int] = None) -> Dict:
        """Synchronous conversion — writes temp file once, passes path to executor."""
        import shutil

        tmp_dir = tempfile.mkdtemp()
        try:
            pdf_path = str(Path(tmp_dir) / "input.pdf")
            Path(pdf_path).write_bytes(pdf_bytes)

            config = self.converter_config.copy()
            if page_range is not None:
                config["page_range"] = page_range
            future = self.executor.submit(self._process_pdf, pdf_path, config)
            return future.result(timeout=3600)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def convert_chunked(self, pdf_bytes: bytes, chunk_ranges: list) -> list[Dict]:
        """Process multiple page ranges from the same PDF. Temp file written once."""
        import shutil

        tmp_dir = tempfile.mkdtemp()
        try:
            pdf_path = str(Path(tmp_dir) / "input.pdf")
            Path(pdf_path).write_bytes(pdf_bytes)

            futures = []
            for page_range in chunk_ranges:
                config = self.converter_config.copy()
                if page_range is not None:
                    config["page_range"] = page_range
                futures.append(self.executor.submit(self._process_pdf, pdf_path, config))

            return [f.result(timeout=3600) for f in futures]
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def __del__(self):
        if hasattr(self, "executor") and self.executor:
            try:
                self.executor.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass


def _worker_init(model_dict):
    import os
    global _worker_model_dict
    _worker_model_dict = model_dict
    print(f"[POOL-WORKER pid={os.getpid()}] initialized", flush=True)
