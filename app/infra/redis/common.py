from typing import Awaitable, TypeVar, cast


class RedisKey(str):
    def __init__(self, value: str):
        super().__init__()
        self.value = value.rstrip(":")

    def __add__(self, other):
        as_str = str(other)
        as_str = as_str.lstrip(":")
        return RedisKey(f"{self}:{as_str}")


KEY_PREFIX = RedisKey("lastliter")
CELERY_KEY_PREFIX = KEY_PREFIX + "celery"

T = TypeVar("T")


def as_awaitable(value: Awaitable[T] | T) -> Awaitable[T]:
    return cast(Awaitable[T], value)
