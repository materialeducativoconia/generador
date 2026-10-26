import asyncio
import signal


async def run() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    print("worker started", flush=True)
    # The job loop (claim → DeepSeek → save) will run here until `stop` is set.
    await stop.wait()
    print("worker stopped", flush=True)


if __name__ == "__main__":
    asyncio.run(run())
