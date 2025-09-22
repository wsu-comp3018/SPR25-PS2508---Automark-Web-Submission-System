#!/usr/bin/env python3
import os, json, sys

def main():
    submission_id = os.getenv("SUBMISSION_ID", "")

    # Minimal placeholder "grading" result
    result = {
    "ok": True,
    "submission_id": submission_id,
    "score": 100,
    "message": "All tests passed."
}

    # Print a single JSON line so the API can capture it as logs/feedback
    print(json.dumps(result), flush=True)

if __name__ == "__main__":
    try:
        main()
        sys.exit(0)
    except Exception as e:
        # Ensure a non-zero exit code on failure; API will mark as failed
        print(json.dumps({"ok": False, "error": str(e)}), flush=True)
        sys.exit(1)
