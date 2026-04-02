import httpx
from core.retry.exponential_backoff import ExponentialBackoffRetry
from core.interfaces import WebhookSender


class HttpWebhookSender(WebhookSender):
    def __init__(self, retry_policy: ExponentialBackoffRetry):
        self.retry_policy = retry_policy

    async def send(self, url: str, payload: dict) -> None:
        async def _post():
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()

        await self.retry_policy.execute(_post)
