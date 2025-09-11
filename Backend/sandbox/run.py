import os, time, json
sid = os.getenv("SUBMISSION_ID", "unknown")
time.sleep(1)
print(json.dumps({"status": "ok", "message": f"sandbox ran for submission {sid}"}))
