import asyncio
import threading
from concurrent.futures import Future
from typing import Any, Coroutine

from app.container import Container
from app.infra.logging import logger


class WorkerAsyncRuntime:
    def __init__(self, container: Container) -> None:
        self.container = container

        self.loop: asyncio.AbstractEventLoop | None = None
        self.thread: threading.Thread | None = None

    def start(self):
        if self.loop is not None:
            return

        logger.info("Starting worker async runtime")

        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(
            target=self._run_loop,
            name="celery-worker-asyncio-loop",
            daemon=True,
        )
        self.thread.start()

        self.run(self._init_resources())

        logger.info("Worker async runtime started")

    def _run_loop(self) -> None:
        assert self.loop is not None

        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    async def _init_resources(self) -> None:
        self.container = Container()

        await self.container.init_resources()  # type: ignore

    def run[T](self, coro: Coroutine[Any, Any, T]) -> T:
        if self.loop is None:
            raise RuntimeError("Worker async runtime is not started")

        future: Future[T] = asyncio.run_coroutine_threadsafe(coro, self.loop)

        return future.result()

    def stop(self) -> None:
        if self.loop is None:
            return

        logger.info("Stopping worker async runtime")

        try:
            self.run(self._shutdown_resources())
        finally:
            loop = self.loop
            thread = self.thread
            loop.call_soon_threadsafe(loop.stop)

            if thread is not None:
                thread.join(timeout=10)

            loop.close()

            self.loop = None
            self.thread = None

        logger.info("Worker async runtime stopped")

    async def _shutdown_resources(self) -> None:
        if self.container is None:
            return

        await self.container.read_engine().dispose()
        await self.container.write_engine().dispose()
        await self.container.shutdown_resources()  # type: ignore


runtime: WorkerAsyncRuntime | None = None


def create_runtime(container: Container) -> WorkerAsyncRuntime:
    global runtime

    if runtime is not None:
        return runtime

    runtime = WorkerAsyncRuntime(container)
    runtime.start()

    return runtime


def stop_runtime() -> None:
    global runtime

    if runtime is None:
        return

    runtime.stop()
    runtime = None


def get_runtime() -> WorkerAsyncRuntime:
    if runtime is None:
        raise RuntimeError("Worker async runtime is not initialized")

    return runtime
