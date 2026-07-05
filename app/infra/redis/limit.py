import asyncio

HARDCODED_SLEEP_SECONDS = 1


class RateLimiter:
    def __init__(self) -> None:
        pass

    async def wait(self, *, key: str, limit_per_second: int) -> None:
        await asyncio.sleep(HARDCODED_SLEEP_SECONDS)
        # TODO: Implement token bucket limiting
