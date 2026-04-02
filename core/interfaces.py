from typing import Protocol, Dict, List


class Converter(Protocol):
    def convert(self, pdf_bytes: bytes, page_range: list[int] = None) -> Dict:
        """
        Returns a dict like:
        {
            "markdown": str,
            "images": List[{"path": str, "bytes": bytes}]
        }
        If page_range is provided, only those pages are converted.
        """
        ...


class WebhookSender(Protocol):
    async def send(self, url: str, payload: dict) -> None:
        ...


class ImageCaptioner(Protocol):
    async def caption(self, image_bytes: bytes, prompt: str) -> str:
        ...

