# Backend/server/app/docker_runner.py
from typing import Tuple
from pathlib import Path
import os
import logging

import docker  # Python Docker SDK

# Set up logging
logger = logging.getLogger(__name__)

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
    logger.info(f"🐳 Starting sandbox container for job {job_id}")
    logger.info(f"📁 Code dir: {code_dir}")
    logger.info(f"📁 Marker dir: {marker_dir}")
    logger.info(f"📁 Results dir: {results_dir}")
    
    client = docker.from_env()

    folder_id = _folder_id_from_marker_dir(marker_dir)
    in_code    = f"{MNT_SUBMISSIONS}/{job_id}/src"
    in_marker  = f"{MNT_ASSIGNMENTS}/{folder_id}/marker" if folder_id else MNT_ASSIGNMENTS
    in_results = f"{MNT_RESULTS}/{job_id}"
    
    logger.info(f"🔧 Container paths - Code: {in_code}, Marker: {in_marker}, Results: {in_results}")

    # Single shell does:
    # - ensure results dir exists and is writable
    # - run marker if markerscript.sh is executable
    cmd = [
        "sh", "-c",
        (
            "set -e; "
            f"mkdir -p '{in_results}'; chmod -R 777 '{in_results}'; "
            f"if [ -x '{in_marker}/markerscript.sh' ]; then "
            f"  RESULT_DIR='{in_results}' CODE_DIR='{in_code}' MARKER_DIR='{in_marker}' '{in_marker}/markerscript.sh'; "
            "else "
            f"  echo 'No executable markerscript.sh at {in_marker}'; exit 2; "
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
        logger.info(f"🏗️  Creating container for job {job_id} using image {JOB_IMAGE}")
        container = client.containers.create(
            image=JOB_IMAGE,
            command=cmd,
            detach=True,
            tty=False,
            stdin_open=False,
            user="root",  # Run as root to have permission to write to volumes
            environment={
                "RESULT_DIR": in_results,
                "CODE_DIR": in_code,
                "MARKER_DIR": in_marker,
            },
            volumes=volumes,
            working_dir="/",
        )
        logger.info(f"✅ Container created: {container.short_id}")
        
        logger.info(f"🚀 Starting container {container.short_id}")
        container.start()
        
        logger.info(f"⏳ Waiting for container {container.short_id} to complete...")
        rc = container.wait()
        exit_code = int(rc.get("StatusCode", 1))
        
        logger.info(f"📋 Container {container.short_id} finished with exit code {exit_code}")
        try:
            logs_text = container.logs(stdout=True, stderr=True).decode("utf-8", "replace")
            logger.info(f"📄 Container {container.short_id} logs captured ({len(logs_text)} chars)")
        finally:
            try:
                logger.info(f"🗑️  Removing container {container.short_id}")
                container.remove(force=True)
                logger.info(f"✅ Container {container.short_id} removed successfully")
            except Exception as e:
                logger.warning(f"⚠️  Failed to remove container {container.short_id}: {e}")
                pass
        
        logger.info(f"🎯 Job {job_id} completed with exit code {exit_code}")
        return exit_code, logs_text

    except Exception as e:
        logger.error(f"❌ Error running job {job_id}: {e}")
        if container is not None:
            try:
                logs_text += container.logs(stdout=True, stderr=True).decode("utf-8", "replace")
                logger.info(f"📄 Error logs captured from container {container.short_id}")
            except Exception as log_e:
                logger.warning(f"⚠️  Failed to capture logs from container {container.short_id}: {log_e}")
                pass
            try:
                logger.info(f"🗑️  Removing failed container {container.short_id}")
                container.remove(force=True)
                logger.info(f"✅ Failed container {container.short_id} removed")
            except Exception as remove_e:
                logger.warning(f"⚠️  Failed to remove failed container {container.short_id}: {remove_e}")
                pass
        logger.error(f"💥 Job {job_id} failed with error: {e}")
        return 1, f"ERROR: {e}\n{logs_text}"
