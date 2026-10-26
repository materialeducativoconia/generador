import signal
import subprocess
import sys


def test_worker_exits_cleanly_on_sigterm():
    # Render sends SIGTERM on every deploy; the worker must stop without an error exit.
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.worker"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        assert "worker started" in proc.stdout.readline()

        proc.send_signal(signal.SIGTERM)

        assert proc.wait(timeout=5) == 0
        assert "worker stopped" in proc.stdout.read()
    finally:
        proc.kill()
