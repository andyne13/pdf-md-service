import base64
from openai import AsyncOpenAI
from core.interfaces import ImageCaptioner
from core.retry.exponential_backoff import ExponentialBackoffRetry


class VlmCaptioner(ImageCaptioner):
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        retry_policy: ExponentialBackoffRetry,
    ):
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url.rstrip("/"),
        )
        self.model = model
        self.retry_policy = retry_policy

    async def caption(self, image_bytes: bytes, prompt: str) -> str:
        b64 = base64.b64encode(image_bytes).decode("utf-8")

        async def _call_vlm():
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{b64}"
                                },
                            },
                        ],
                    }
                ],
            )
            return response.choices[0].message.content

        return await self.retry_policy.execute(_call_vlm)
