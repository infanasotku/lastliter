from celery import Task

from app.infra.common.correlation import RequestContext, with_request_context
from app.infra.logging import logger


def as_task(func) -> Task:
    return func


class BaseTask(Task):
    abstract = True

    def __call__(self, *args, **kwargs):
        with with_request_context(RequestContext(request_id=self.request.id)):
            logger.info(
                "Task is starting",
                extra={
                    "task_id": self.request.id,
                    "task_name": self.name,
                },
            )

            try:
                return super().__call__(*args, **kwargs)
            except Exception:
                logger.exception(
                    "Task failed",
                    extra={
                        "task_id": self.request.id,
                        "task_name": self.name,
                    },
                )
                raise
            finally:
                logger.info(
                    "Task finished",
                    extra={
                        "task_id": self.request.id,
                        "task_name": self.name,
                    },
                )
