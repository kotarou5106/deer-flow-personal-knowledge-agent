from __future__ import annotations

import asyncio
import logging
import os
import signal
from collections.abc import Awaitable, Callable, Mapping

from app.knowledge_runtime import (
    KnowledgeRuntime,
    KnowledgeWorkerConfigError,
    build_knowledge_runtime,
    parse_knowledge_worker_settings,
)

logger = logging.getLogger(__name__)

RuntimeFactory = Callable[..., Awaitable[KnowledgeRuntime]]


async def run_worker(
    *,
    environ: Mapping[str, str | None] | None = None,
    shutdown_event: asyncio.Event | None = None,
    register_signals: bool = True,
    runtime_factory: RuntimeFactory = build_knowledge_runtime,
) -> int:
    values = environ if environ is not None else os.environ
    database_url = (values.get("KNOWLEDGE_DATABASE_URL") or "").strip()
    if not database_url:
        logger.error("KNOWLEDGE_DATABASE_URL is required to start Knowledge Worker")
        return 2

    try:
        settings = parse_knowledge_worker_settings(values)
    except KnowledgeWorkerConfigError:
        logger.exception("Invalid Knowledge Worker configuration")
        return 2

    stop_event = shutdown_event or asyncio.Event()
    cleanup_signals = _install_signal_handlers(stop_event) if register_signals else (lambda: None)
    runtime: KnowledgeRuntime | None = None
    exit_code = 0
    try:
        runtime = await runtime_factory(database_url, worker_settings=settings, start_worker=True)
        logger.info("Knowledge Worker started")
        await stop_event.wait()
    except Exception:
        logger.exception("Knowledge Worker failed")
        exit_code = 1
    finally:
        cleanup_signals()
        if runtime is not None:
            try:
                await runtime.close(timeout_seconds=settings.shutdown_timeout_seconds)
            except Exception:
                logger.exception("Knowledge Worker shutdown failed")
                exit_code = 1
    return exit_code


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    raise SystemExit(asyncio.run(run_worker()))


def _install_signal_handlers(stop_event: asyncio.Event) -> Callable[[], None]:
    loop = asyncio.get_running_loop()
    signals = (signal.SIGINT, signal.SIGTERM)
    installed: list[signal.Signals] = []

    def request_stop() -> None:
        stop_event.set()

    try:
        for sig in signals:
            loop.add_signal_handler(sig, request_stop)
            installed.append(sig)

        def cleanup() -> None:
            for sig in installed:
                loop.remove_signal_handler(sig)

        return cleanup
    except (NotImplementedError, RuntimeError):
        previous: dict[signal.Signals, signal.Handlers] = {}

        def handler(signum: int, _frame: object) -> None:
            stop_event.set()
            old = previous.get(signal.Signals(signum))
            if callable(old):
                old(signum, _frame)

        for sig in signals:
            previous[sig] = signal.getsignal(sig)
            signal.signal(sig, handler)

        def cleanup() -> None:
            for sig, old in previous.items():
                signal.signal(sig, old)

        return cleanup


if __name__ == "__main__":
    main()
