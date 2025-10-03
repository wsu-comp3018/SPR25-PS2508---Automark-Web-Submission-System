# app/worker.py
import os
import sqlite3
import datetime
import time
import traceback
from pathlib import Path
import subprocess

from . import storage, docker_runner

# --- Minimal SVN export used by main.py and the worker loop ---
def svn_export(url: str, rev: int, dest: str):
    # Export the exact revision to dest, overwriting if exists
    subprocess.run(
        ["svn", "export", "-r", str(rev), url, dest, "--force"],
        check=True, text=True, capture_output=True
    )

# Use the same DB path as main.py (env override supported)
DB_PATH = os.getenv("DB_PATH", "/app/automark.db")

def _conn():
    return sqlite3.connect(DB_PATH)

def _iso_now():
    return datetime.datetime.utcnow().isoformat() + "Z"

def _next_job():
    with _conn() as c:
        c.row_factory = sqlite3.Row
        return c.execute(
            """SELECT id, folder_id, svn_url, revision
               FROM svn_jobs
               WHERE status='queued'
               ORDER BY id
               LIMIT 1"""
        ).fetchone()

def _update_job(job_id: int, **kv):
    keys = ", ".join([f"{k}=?" for k in kv])
    vals = list(kv.values()) + [job_id]
    with _conn() as c:
        c.execute(f"UPDATE svn_jobs SET {keys} WHERE id=?", vals)

def loop(poll_interval: float = 0.5):
    while True:
        row = _next_job()
        if not row:
            time.sleep(poll_interval)
            continue

        job_id = row["id"]
        folder_id = row["folder_id"]
        url = row["svn_url"]
        rev = int(row["revision"])

        _update_job(job_id, status="running", started_at=_iso_now())

        # Paths consistent with main.py
        code_dir    = storage.SUBMISSIONS_BASE / str(job_id) / "src"
        results_dir = storage.RESULTS_BASE / str(job_id)
        marker_dir  = storage.ASSIGN_BASE / str(folder_id) / "marker"
        code_dir.mkdir(parents=True, exist_ok=True)
        results_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 1) Export code
            svn_export(url, rev, str(code_dir))

            # 2) Run marker
            exit_code, logs = docker_runner.run_job(job_id, code_dir, marker_dir, results_dir)

            # 3) Persist logs
            log_path = results_dir / "runner.log"
            log_path.write_text(logs or "", encoding="utf-8")

            # 4) Update job status
            _update_job(
                job_id,
                status="completed" if exit_code == 0 else "failed",
                exit_code=int(exit_code),
                finished_at=_iso_now(),
                result_path=str(results_dir),
                log_path=str(log_path),
            )
        except Exception:
            # Best-effort log write
            try:
                (results_dir / "runner.log").write_text(traceback.format_exc(), encoding="utf-8")
            except Exception:
                pass
            _update_job(job_id, status="failed", finished_at=_iso_now())
        finally:
            time.sleep(0.2)  # small back-off between jobs

def start_async():
    import threading
    t = threading.Thread(target=loop, daemon=True)
    t.start()
