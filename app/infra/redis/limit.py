import asyncio
import random


class RateLimiter:
    def __init__(self) -> None:
        pass

    async def wait(self, *, key: str, limit_per_second: int) -> None:
        await asyncio.sleep(random.uniform(1, 5))
        # TODO: Implement token bucket limiting
