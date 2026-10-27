import os
import signal
import subprocess
import sys

from tests.db.conftest import LOCAL_SUPABASE_DB_URL


def test_worker_exits_cleanly_on_sigterm(raw_db):  # raw_db: skip when local Supabase is down
    # Render sends SIGTERM on every deploy; the worker must stop without an error exit.
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.worker"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env={**os.environ, "DATABASE_URL": LOCAL_SUPABASE_DB_URL, "SUPABASE_URL": "http://127.0.0.1:55321",
             "DEEPSEEK_API_KEY": "test", "SUPABASE_SERVICE_ROLE_KEY": "test"},
    )
    try:
        assert "worker started" in proc.stdout.readline()

        proc.send_signal(signal.SIGTERM)

        assert proc.wait(timeout=5) == 0
        assert "worker stopped" in proc.stdout.read()
    finally:
        proc.kill()
