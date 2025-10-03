# app/storage.py
from pathlib import Path
import os

ASSIGN_BASE     = Path(os.getenv("ASSIGN_BASE", "/app/data/assignments"))
RESULTS_BASE    = Path(os.getenv("RESULTS_BASE", "/app/data/results"))
SUBMISSIONS_BASE= Path(os.getenv("SUBMISSIONS_BASE", "/app/shared/submissions"))
              # job outputs/logs

def assign_marker_dir(aid: int) -> Path:
    p = ASSIGN_BASE / str(aid) / "marker"
    p.mkdir(parents=True, exist_ok=True)
    return p

def submission_src_dir(sid: int) -> Path:
    p = SUBMISSIONS_BASE / str(sid) / "src"
    p.mkdir(parents=True, exist_ok=True)
    return p

def submission_results_dir(sid: int) -> Path:
    p = RESULTS_BASE / str(sid)
    p.mkdir(parents=True, exist_ok=True)
    return p
