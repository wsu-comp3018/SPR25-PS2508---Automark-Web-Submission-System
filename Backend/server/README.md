# Backend / Server

This folder contains the backend for the AutoMark system.  
At this stage, only the **minimal structure** is set up.

## Structure
- `app/` → Application entrypoint (`main.py`).
- `automark/` → Runtime storage. Includes:
  - `incoming/` → Uploaded files waiting for processing.
  - `submissions/<TERM>/` → Organized by academic term (e.g., `2025-AUT`).
- `config/` → Configuration files (`paths.yaml`, `settings.example.env`).
- `requirements.txt` → Python dependencies (to be populated later).
- `Makefile` → Common build/run commands (to be populated later).

## Notes
- More modules (runner, queue, models, utils, etc.) will be added in later milestones.  
- This lean skeleton ensures the repo stays lightweight while allowing incremental growth.
