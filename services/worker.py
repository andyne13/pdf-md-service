import asyncio
import logging

import ray

logger = logging.getLogger("ray.serve")


@ray.remote(num_gpus=0.01, max_restarts=5, max_concurrency=50)
class MarkerWorkerActor:
    def __init__(self, pool_workers: int = 4):
        from core.converters.marker_converter import MarkerPdfConverter

        self.converter = MarkerPdfConverter(max_processes=pool_workers)
        logger.info("MarkerWorkerActor initialized with %d pool workers", pool_workers)

    async def convert_pdf(self, pdf_bytes: bytes, page_range: list[int] = None) -> dict:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.converter.convert, pdf_bytes, page_range
        )

    async def convert_pdf_chunked(self, pdf_bytes: bytes, chunk_ranges: list) -> list[dict]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.converter.convert_chunked, pdf_bytes, chunk_ranges
        )
