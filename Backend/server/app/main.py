# Backend/server/app/main.py
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Request, status as http_status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import Optional
import hashlib, sqlite3, uuid, datetime
import os

# Optional Docker SDK (API should still run if Docker isn't available)
try:
    import docker
except Exception:
    docker = None

DB_PATH = os.getenv("DB_PATH", "automark.db")
SANDBOX_IMAGE = os.getenv("SANDBOX_IMAGE", "automark-sandbox:latest")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Users
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT CHECK(role IN ('student','lecturer')) NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            last_login TEXT
        )
    """)

    # Sessions
    c.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Minimal submissions table (status lifecycle managed by API)
    c.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folder_id INTEGER,
            student_id INTEGER NOT NULL,
            submitted_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'submitted',
            FOREIGN KEY (student_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()

def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()

def now_iso():
    return datetime.datetime.utcnow().isoformat() + "Z"

def update_submission_status(submission_id: int, status: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE submissions SET status = ? WHERE id = ?", (status, submission_id))
    conn.commit()
    conn.close()

app = FastAPI(title="Automark API", version="0.2.0")

# CORS for dev (relax now, tighten later)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Models ----------
class RegisterIn(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: str
    first_name: str
    last_name: str

class RegisterOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    role: str
    first_name: str
    last_name: str

class LoginIn(BaseModel):
    username: str  # username or email
    password: str
    remember_me: bool = False

class LoginOut(BaseModel):
    success: bool
    message: str
    token: Optional[str] = None
    user: Optional[dict] = None

class SubmissionReceiveIn(BaseModel):
    folder_id: Optional[int] = None
    content: Optional[str] = None

class SubmissionReceiveOut(BaseModel):
    submission_id: int
    status: str  # queued

# ---------- Helpers ----------
def get_user_from_token(token: str):
    """Return user dict if token valid & active, else None."""
    now = datetime.datetime.utcnow().isoformat() + "Z"
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT s.token, s.is_active, s.expires_at,
               u.id, u.username, u.email, u.role, u.first_name, u.last_name, u.is_active
        FROM sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.token = ?
    """, (token,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    _, s_active, expires_at, uid, username, email, role, first_name, last_name, u_active = row
    if s_active != 1 or u_active != 1 or now > expires_at:
        return None
    return {
        "id": uid,
        "username": username,
        "email": email,
        "role": role,
        "firstName": first_name,
        "lastName": last_name
    }

def get_current_user(request: Request):
    """FastAPI dependency: read Bearer token and return user dict."""
    auth = request.headers.get("Authorization", "")
    token = None
    if auth.startswith("Bearer "):
        token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    user = get_user_from_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return user

def launch_sandbox_container(submission_id: int):
    """
    Start a sandbox container for this submission.
    Status flow: queued -> running -> completed/failed/error
    """
    # If Docker SDK missing, mark error and bail (keeps API usable in dev).
    if not docker:
        update_submission_status(submission_id, "error")
        print(f"[sandbox] Docker SDK unavailable; submission {submission_id} marked error")
        return

    client = None
    try:
        update_submission_status(submission_id, "running")
        client = docker.from_env()

        container = client.containers.run(
            image=SANDBOX_IMAGE,
            environment={"SUBMISSION_ID": str(submission_id)},
            labels={"automark": "sandbox", "submission_id": str(submission_id)},
            # For dev clarity keep the container until we collect exit status:
            detach=True,
            remove=False,
            network_mode="none",     # isolate; adjust later if needed
            mem_limit="512m",
            pids_limit=256
        )

        # Wait for job to finish and update status.
        result = container.wait()  # {'StatusCode': int}
        code = (result or {}).get("StatusCode", 1)
        if code == 0:
            update_submission_status(submission_id, "completed")
        else:
            update_submission_status(submission_id, "failed")

    except Exception as e:
        update_submission_status(submission_id, "error")
        print(f"[sandbox] error for submission {submission_id}: {e}")
    finally:
        # Try to clean up the container if it still exists
        try:
            if client and 'container' in locals():
                container.remove(force=True)
        except Exception:
            pass

# ---------- Routes ----------
@app.on_event("startup")
def _startup():
    init_db()

@app.get("/")
def read_root():
    return {"message": "Hello, Automark!"}

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "automark", "version": "0.2.0"}

@app.get("/api/v1/ping")
def ping():
    return {"pong": True}

@app.post("/api/v1/auth/register", response_model=RegisterOut)
def register(body: RegisterIn):
    init_db() 
    body.role = body.role.lower()
    if body.role not in ("student", "lecturer"):
        raise HTTPException(400, "role must be 'student' or 'lecturer'")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO users (username, email, password_hash, role, first_name, last_name, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            body.username.strip(),
            body.email.strip().lower(),
            hash_password(body.password),
            body.role,
            body.first_name.strip(),
            body.last_name.strip(),
            now_iso(),
        ))
        user_id = c.lastrowid
        conn.commit()
    except sqlite3.IntegrityError as e:
        conn.close()
        msg = "Username already exists" if "username" in str(e).lower() else "Email already exists"
        raise HTTPException(409, msg)
    c.execute("SELECT id, username, email, role, first_name, last_name FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return RegisterOut(
        id=row[0], username=row[1], email=row[2], role=row[3],
        first_name=row[4], last_name=row[5]
    )

@app.post("/api/v1/auth/login", response_model=LoginOut)
def login(body: LoginIn):
    u = body.username.strip()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # find by username OR email
    c.execute("""
        SELECT id, username, email, password_hash, role, first_name, last_name, is_active
        FROM users WHERE username = ? OR email = ?
    """, (u, u.lower()))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(401, "Invalid username/email or password")

    user_id, username, email, pw_hash, role, first_name, last_name, is_active = row
    if is_active != 1 or pw_hash != hash_password(body.password):
        conn.close()
        raise HTTPException(401, "Invalid username/email or password")

    token = uuid.uuid4().hex
    ttl_days = 30 if body.remember_me else 1
    created = datetime.datetime.utcnow()
    expires = created + datetime.timedelta(days=ttl_days)

    c.execute("UPDATE users SET last_login = ? WHERE id = ?", (now_iso(), user_id))
    c.execute("""
        INSERT INTO sessions (token, user_id, created_at, expires_at, is_active)
        VALUES (?, ?, ?, ?, 1)
    """, (token, user_id, created.isoformat() + "Z", expires.isoformat() + "Z"))
    conn.commit()
    conn.close()

    return LoginOut(
        success=True,
        message="Login successful",
        token=token,
        user={
            "id": user_id,
            "username": username,
            "email": email,
            "role": role,
            "firstName": first_name,
            "lastName": last_name
        }
    )

@app.get("/api/v1/auth/session/{token}")
def validate_session(token: str):
    now = datetime.datetime.utcnow().isoformat() + "Z"
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT s.token, s.is_active, s.expires_at, u.id, u.username, u.email, u.role, u.first_name, u.last_name, u.is_active
        FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ?
    """, (token,))
    row = c.fetchone()
    conn.close()
    if not row:
        return {"valid": False, "message": "Invalid session"}
    _, s_active, expires_at, uid, username, email, role, first_name, last_name, u_active = row
    if s_active != 1 or u_active != 1 or now > expires_at:
        return {"valid": False, "message": "Session expired or inactive"}
    return {
        "valid": True,
        "user": {
            "id": uid,
            "username": username,
            "email": email,
            "role": role,
            "firstName": first_name,
            "lastName": last_name
        }
    }

# ---------- Submission → sandbox trigger ----------
@app.post(
    "/api/v1/submissions/receive",
    response_model=SubmissionReceiveOut,
    status_code=http_status.HTTP_202_ACCEPTED,
)
def receive_submission(
    body: SubmissionReceiveIn,
    background: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    if current_user["role"] != "student":
        raise HTTPException(status_code=403, detail="Only students can submit")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO submissions (folder_id, student_id, submitted_at, status)
            VALUES (?, ?, ?, 'submitted')
        """, (body.folder_id, current_user["id"], now_iso()))
        submission_id = c.lastrowid
        conn.commit()
    finally:
        conn.close()

    # mark queued and schedule sandbox container
    update_submission_status(submission_id, "queued")
    background.add_task(launch_sandbox_container, submission_id=submission_id)
    return SubmissionReceiveOut(submission_id=submission_id, status="queued")

@app.get("/api/v1/submissions/{submission_id}")
def get_submission(submission_id: int, current_user: dict = Depends(get_current_user)):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, folder_id, student_id, submitted_at, status FROM submissions WHERE id = ?", (submission_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Submission not found")

    sid, folder_id, student_id, submitted_at, status_val = row

    # Students can only view their own submission; lecturers can view all
    if current_user["role"] != "lecturer" and student_id != current_user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")

    return {
        "id": sid,
        "folder_id": folder_id,
        "student_id": student_id,
        "submitted_at": submitted_at,
        "status": status_val,
    }
