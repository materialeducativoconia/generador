"""Worker process: claims jobs from Postgres and runs up to DEEPSEEK_MAX_INFLIGHT of them at once.

Exactly one instance runs, so the in-memory rate limiter in app.llm is global (ARCHITECTURE.md §5.2).
"""

import asyncio
import logging
import signal
import socket

from app.config import Settings
from app.db import make_engine
from app.jobs import Deps, claim_job, process_job, reap_stale_jobs
from app.images import OpenRouterImages
from app.llm import DeepSeek
from app.research import Web
from app.vision import OpenRouterVision
from app.storage import Storage

log = logging.getLogger("worker")
IDLE_POLL_SECONDS = 1.0
REAP_EVERY_SECONDS = 60
SHUTDOWN_GRACE_SECONDS = 25  # Render waits 30 s after SIGTERM


async def run(stop: asyncio.Event | None = None) -> None:
    """Runs until `stop` is set; standalone (stop=None) it stops on SIGTERM/SIGINT."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings()
    engine = make_engine(settings.database_url, pool_size=5)
    deps = Deps(
        engine=engine,
        llm=DeepSeek(settings.deepseek_api_key, settings.deepseek_model, settings.deepseek_rpm,
                     settings.deepseek_max_inflight),
        storage=Storage(settings.supabase_url, settings.supabase_service_role_key),
        images=OpenRouterImages(settings.openrouter_api_key, settings.openrouter_image_model)
        if settings.openrouter_api_key else None,
        vision=OpenRouterVision(settings.openrouter_api_key, settings.openrouter_review_model)
        if settings.openrouter_api_key else None,
        web=Web(),
    )
    worker_id = f"{socket.gethostname()}:{id(deps)}"
    # More jobs in flight than LLM slots: PDF exports and waits on the limiter shouldn't block the queue.
    slots = asyncio.Semaphore(settings.deepseek_max_inflight + 4)
    running: set[asyncio.Task] = set()

    loop = asyncio.get_running_loop()
    if stop is None:
        stop = asyncio.Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)

    async def run_one(job):
        try:
            await process_job(deps, job)
        finally:
            slots.release()

    print("worker started", flush=True)
    last_reap = 0.0
    while not stop.is_set():
        try:
            if loop.time() - last_reap > REAP_EVERY_SECONDS:
                if reaped := await reap_stale_jobs(engine):
                    log.warning("requeued %s stale jobs", reaped)
                last_reap = loop.time()
            await slots.acquire()
            job = await claim_job(engine, worker_id)
            if job is None:
                slots.release()
                await _sleep_unless(stop, IDLE_POLL_SECONDS)
                continue
            log.info("job %s %s attempt %s", job["id"], job["kind"], job["attempts"])
            task = asyncio.create_task(run_one(job))
            running.add(task)
            task.add_done_callback(running.discard)
        except Exception:  # DB blip: back off instead of crashing the process
            log.exception("worker loop error")
            await _sleep_unless(stop, 5)

    if running:
        # Jobs still running after the grace period stay `running`; the reaper requeues them.
        await asyncio.wait(running, timeout=SHUTDOWN_GRACE_SECONDS)
    await engine.dispose()
    print("worker stopped", flush=True)


async def _sleep_unless(stop: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), seconds)
    except TimeoutError:
        pass


if __name__ == "__main__":
    asyncio.run(run())
