from celery import Celery, signals

from app.container import Container
from app.infra.celery.runtime import create_runtime, stop_runtime
from app.infra.celery.task import BaseTask
from app.infra.logging import create_logger, logger
from app.infra.redis.common import KEY_PREFIX

create_logger(with_process_name=True)


@signals.setup_logging.connect()
def setup_celery_logging(**kwargs):
    pass


def create_app():
    logger.info("Creating worker application")
    container = Container()
    settings = container.settings()

    app = Celery(
        "lastliter-worker",
        broker=str(settings.rabbitmq.dsn),
        backend=str(settings.redis.dsn),
        result_backend_transport_options={
            "global_keyprefix": str(KEY_PREFIX) + ":",
        },
        worker_hijack_root_logger=False,
        #
        task_cls=BaseTask,
        #
        include=["app.controllers.tasks"],
    )

    @signals.worker_process_init.connect(weak=False)
    def on_worker_process_init(**kwargs):
        container = Container()
        container.wire(packages=["app.controllers.tasks"])

        create_runtime(container)

    @signals.worker_process_shutdown.connect(weak=False)
    def on_worker_process_shutdown(**kwargs):
        stop_runtime()

    logger.info("Worker application created")
    return app


app = create_app()
