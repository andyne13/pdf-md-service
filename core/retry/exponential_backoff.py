# core/retry/exponential_backoff.py
import asyncio
import random
from typing import Callable, Any, Iterable, Type


class ExponentialBackoffRetry:
    def __init__(
        self,
        max_retries: int = 5,
        base_delay: float = 0.5,
        max_delay: float = 10.0,
        jitter: float = 0.2,
        retry_exceptions: Iterable[Type[Exception]] = (Exception,),
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter
        self.retry_exceptions = tuple(retry_exceptions)

    async def execute(self, func: Callable[..., Any], *args, **kwargs):
        attempt = 0

        while True:
            try:
                return await func(*args, **kwargs)

            except self.retry_exceptions as e:
                attempt += 1
                if attempt > self.max_retries:
                    raise

                delay = min(self.base_delay * (2 ** (attempt - 1)), self.max_delay)
                delay *= 1 + random.uniform(-self.jitter, self.jitter)

                await asyncio.sleep(delay)

