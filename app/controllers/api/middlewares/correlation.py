import uuid

from starlette.responses import JSONResponse

from app.infra.common.correlation import RequestContext, with_request_context
from app.infra.logging.logger import get_logger

CORRELATION_ID_HEADER = "X-Request-ID"

logger = get_logger().getChild(__name__)


class CorrelationIdASGIMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        request_id = str(uuid.uuid4())
        method = scope.get("method")
        path = scope.get("path")

        response_started = False
        response_completed = False
        status_code = None

        async def send_wrapper(message):
            nonlocal response_started, response_completed, status_code
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
            elif message["type"] == "http.response.body" and not message.get("more_body", False):
                response_completed = True
            await send(message)

        with with_request_context(RequestContext(request_id=request_id)):
            logger.info(f"HTTP request started: method={method} path={path}")
            try:
                await self.app(scope, receive, send_wrapper)
            except Exception:
                logger.exception("Unhandled exception while handling request")

                if response_started or response_completed:
                    return

                resp = JSONResponse(
                    {
                        "detail": "Internal Server Error",
                        CORRELATION_ID_HEADER: request_id,
                    },
                    status_code=500,
                )
                await resp(scope, receive, send)
                return
            else:
                logger.info(
                    f"HTTP request completed: method={method} path={path} status_code={status_code}",
                )
