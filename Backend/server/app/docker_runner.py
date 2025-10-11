# Backend/server/app/docker_runner.py
from typing import Tuple
from pathlib import Path
import os

import docker  # Python Docker SDK

# Image to run the marker inside
JOB_IMAGE = os.getenv("JOB_IMAGE", "automark-job:latest")

# Named volumes (must match docker-compose)
VOL_SUBMISSIONS = "automark-submissions"
VOL_ASSIGNMENTS = "automark-assignments"
VOL_RESULTS     = "automark-results"

# In-container mount points for those volumes
MNT_SUBMISSIONS = "/mnt/submissions"
MNT_ASSIGNMENTS = "/mnt/assignments"
MNT_RESULTS     = "/mnt/results"


def _folder_id_from_marker_dir(marker_dir) -> str:
    """
    Try to infer <folder_id> from a path like .../<folder_id>/marker.
    Falls back to the last numeric component if needed.
    """
    try:
        p = Path(str(marker_dir)).resolve()
        if p.name == "marker":
            return p.parent.name
        for part in reversed(p.parts):
            if part.isdigit():
                return part
    except Exception:
        pass
    return ""


def run_job(job_id: int, code_dir, marker_dir, results_dir) -> Tuple[int, str]:
    """
    Launch the marker in a container using named volumes:
      - code:   /mnt/submissions/<job_id>/src
      - marker: /mnt/assignments/<folder_id>/marker/run.sh
      - output: /mnt/results/<job_id>

    We do NOT bind host paths directly (avoids macOS file sharing issues).
    """
    client = docker.from_env()

    folder_id = _folder_id_from_marker_dir(marker_dir)
    in_code    = f"{MNT_SUBMISSIONS}/{job_id}/src"
    in_marker  = f"{MNT_ASSIGNMENTS}/{folder_id}/marker" if folder_id else MNT_ASSIGNMENTS
    in_results = f"{MNT_RESULTS}/{job_id}"

    # Single shell does:
    # - ensure results dir exists and is writable
    # - run marker if run.sh is executable
    cmd = [
        "bash", "-lc",
        (
            "set -euo pipefail; "
            f"mkdir -p '{in_results}'; chmod -R 777 '{in_results}' || true; "
            f"if [ -x '{in_marker}/run.sh' ]; then "
            f"  RESULT_DIR='{in_results}' CODE_DIR='{in_code}' MARKER_DIR='{in_marker}' '{in_marker}/run.sh'; "
            "else "
            f"  echo 'No executable run.sh at {in_marker}'; exit 2; "
            "fi"
        )
    ]

    # Map named volumes into the container
    volumes = {
        VOL_SUBMISSIONS: {"bind": MNT_SUBMISSIONS, "mode": "rw"},
        VOL_ASSIGNMENTS: {"bind": MNT_ASSIGNMENTS, "mode": "rw"},
        VOL_RESULTS:     {"bind": MNT_RESULTS,     "mode": "rw"},
    }

    container = None
    logs_text = ""
    try:
        container = client.containers.create(
            image=JOB_IMAGE,
            command=cmd,
            detach=True,
            tty=False,
            stdin_open=False,
            environment={
                "RESULT_DIR": in_results,
                "CODE_DIR": in_code,
                "MARKER_DIR": in_marker,
            },
            volumes=volumes,
            working_dir="/",
        )
        container.start()
        rc = container.wait()
        exit_code = int(rc.get("StatusCode", 1))
        try:
            logs_text = container.logs(stdout=True, stderr=True).decode("utf-8", "replace")
        finally:
            try:
                container.remove(force=True)
            except Exception:
                pass
        return exit_code, logs_text

    except Exception as e:
        if container is not None:
            try:
                logs_text += container.logs(stdout=True, stderr=True).decode("utf-8", "replace")
            except Exception:
                pass
            try:
                container.remove(force=True)
            except Exception:
                pass
        return 1, f"ERROR: {e}\n{logs_text}"
