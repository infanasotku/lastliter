from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass
class RequestContext:
    request_id: str


_correlation_id = ContextVar("correlation_id", default=None)


def get_request_context() -> RequestContext:
    ctx = _correlation_id.get()
    if not ctx:
        raise ValueError("Request context not found")
    return ctx


def get_request_context_save() -> RequestContext | None:
    return _correlation_id.get()


@contextmanager
def with_request_context(request_context: RequestContext):
    token = _correlation_id.set(request_context)  # type: ignore
    try:
        yield
    finally:
        _correlation_id.reset(token)
