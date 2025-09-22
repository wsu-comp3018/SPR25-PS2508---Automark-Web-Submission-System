# Backend/server/app/main.py
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
import hashlib, sqlite3, uuid, datetime
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import logging

import uuid


import os
from typing import List, Optional, Dict
import json
from contextlib import asynccontextmanager
import threading, time, traceback

# print("Current working directory:", os.getcwd())
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
# print("STATIC_DIR exists?", STATIC_DIR.exists(), BASE_DIR)
# print("Files inside STATIC_DIR:", list(STATIC_DIR.rglob("*")))

import sys
sys.path.append('/app')
from ssh_user_manager import create_ssh_user_for_registration

DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "automark.db"))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to import Docker SDK; if missing, we simulate job runs
try:
    import docker  # Python Docker SDK
except Exception:
    docker = None

def init_db():
    try:
        print(f"🗃️ INIT_DB: Connecting to {DB_PATH}")
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        c = conn.cursor()

        # Pragmas to reduce lock errors and enforce FK
        c.execute("PRAGMA journal_mode=WAL;")
        c.execute("PRAGMA foreign_keys=ON;")
        c.execute("PRAGMA busy_timeout=3000;")

        print("📝 INIT_DB: Creating users table...")
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

        print("📝 INIT_DB: Creating sessions table...")
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

        print("📝 INIT_DB: Creating folders table...")
        c.execute("""
            CREATE TABLE IF NOT EXISTS folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                due_date TEXT,
                max_points INTEGER DEFAULT 100,
                status TEXT DEFAULT 'draft',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                lecturer_id INTEGER NOT NULL,
                FOREIGN KEY (lecturer_id) REFERENCES users(id)
            )
        """)

        print("📝 INIT_DB: Creating folder_assignments table...")
        c.execute("""
            CREATE TABLE IF NOT EXISTS folder_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                assigned_at TEXT NOT NULL,
                FOREIGN KEY (folder_id) REFERENCES folders(id),
                FOREIGN KEY (student_id) REFERENCES users(id),
                UNIQUE(folder_id, student_id)
            )
        """)

        print("📝 INIT_DB: Creating submissions table...")
        c.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                submitted_at TEXT NOT NULL,
                score INTEGER,
                feedback TEXT,
                status TEXT DEFAULT 'submitted',
                graded_at TEXT,
                FOREIGN KEY (folder_id) REFERENCES folders(id),
                FOREIGN KEY (student_id) REFERENCES users(id)
            )
        """)

        # Helpful indexes
        c.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_submissions_folder_student ON submissions(folder_id, student_id);")

        print("🔧 INIT_DB: Applying schema self-migrations (no-ops if already applied)...")

        def ensure_columns(table: str, specs: dict[str, str]) -> None:
            cur = conn.cursor()
            cur.execute(f"PRAGMA table_info({table});")
            existing = {row[1] for row in cur.fetchall()}  # row[1] = column name
            to_add = [(name, ddl) for name, ddl in specs.items() if name not in existing]
            for name, ddl in to_add:
                print(f"   ➕ {table}.{name}  (ALTER TABLE ... ADD COLUMN {ddl})")
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
            if to_add:
                conn.commit()

        # Make sure older DBs gain the newer columns
        ensure_columns("submissions", {
            "score": "INTEGER",
            "feedback": "TEXT",
            "status": "TEXT DEFAULT 'submitted'",
            "graded_at": "TEXT",
        })

        print("📝 INIT_DB: Creating subjects table...")
        c.execute("""
            CREATE TABLE IF NOT EXISTS subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                lecturer_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (lecturer_id) REFERENCES users(id)
            )
        """)
        
        print("📝 INIT_DB: Creating subject_enrollments table...")
        c.execute("""
            CREATE TABLE IF NOT EXISTS subject_enrollments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                subject_id INTEGER NOT NULL,
                enrolled_at TEXT NOT NULL,
                semester TEXT NOT NULL CHECK(semester IN ('AUT','SPR')),
                year INTEGER NOT NULL,
                status TEXT DEFAULT 'active' CHECK(status IN ('active','dropped','completed')),
                FOREIGN KEY (student_id) REFERENCES users(id),
                FOREIGN KEY (subject_id) REFERENCES subjects(id),
                UNIQUE(student_id, subject_id, semester, year)
            )
        """)
        
        print("📝 INIT_DB: Creating assignment_templates table...")
        c.execute("""
            CREATE TABLE IF NOT EXISTS assignment_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                semester TEXT NOT NULL CHECK(semester IN ('AUT','SPR')),
                year INTEGER NOT NULL,
                assignment_number INTEGER NOT NULL,
                template_files TEXT,  -- JSON string of template files
                svn_path TEXT,  -- SVN repository path
                due_date TEXT,
                max_points INTEGER DEFAULT 100,
                status TEXT DEFAULT 'draft' CHECK(status IN ('draft','published','archived')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                created_by INTEGER NOT NULL,
                FOREIGN KEY (subject_id) REFERENCES subjects(id),
                FOREIGN KEY (created_by) REFERENCES users(id),
                UNIQUE(subject_id, semester, year, assignment_number)
            )
        """)
        
        print("👨‍🏫 INIT_DB: Creating hardcoded lecturers...")
        
        # Hardcoded lecturer information
        lecturers = [
            {
                "username": "lecturer_db",
                "email": "db.lecturer@automark.com",
                "password": "dbpassword123",
                "first_name": "John",
                "last_name": "Smith",
                "subjects": [
                    {"code": "Comp0067", "name": "Database and Design"}
                ]
            },
            {
                "username": "lecturer_prog",
                "email": "prog.lecturer@automark.com", 
                "password": "progpassword123",
                "first_name": "Sarah",
                "last_name": "Johnson",
                "subjects": [
                    {"code": "Comp0420", "name": "Programming Techniques"}
                ]
            },
            {
                "username": "lecturer_oop",
                "email": "oop.lecturer@automark.com",
                "password": "ooppassword123", 
                "first_name": "Robert",
                "last_name": "Williams",
                "subjects": [
                    {"code": "Infs8586", "name": "Object Oriented Programming"},
                    {"code": "Comp5055", "name": "Software Engineering"}
                ]
            }
        ]

        now = now_iso()
        
        for lecturer in lecturers:
            try:
                # Check if lecturer already exists
                c.execute("SELECT id FROM users WHERE username = ?", (lecturer["username"],))
                existing_user = c.fetchone()
                
                if not existing_user:
                    # Create lecturer user
                    c.execute("""
                        INSERT INTO users (username, email, password_hash, role, first_name, last_name, created_at)
                        VALUES (?, ?, ?, 'lecturer', ?, ?, ?)
                    """, (
                        lecturer["username"],
                        lecturer["email"],
                        hash_password(lecturer["password"]),
                        lecturer["first_name"],
                        lecturer["last_name"],
                        now
                    ))
                    lecturer_id = c.lastrowid
                    print(f"✅ Created lecturer: {lecturer['username']} (ID: {lecturer_id})")
                    
                    # Create SSH user for lecturer
                    try:
                        ssh_result = create_ssh_user_for_registration(lecturer["username"], lecturer["password"])
                        if ssh_result["success"]:
                            print(f"✅ Created SSH user for {lecturer['username']}")
                        else:
                            print(f"⚠️  SSH user creation failed for {lecturer['username']}: {ssh_result.get('error')}")
                    except Exception as e:
                        print(f"⚠️  SSH user creation error for {lecturer['username']}: {e}")
                    
                    # Assign subjects to lecturer
                    for subject in lecturer["subjects"]:
                        try:
                            c.execute("""
                                INSERT OR IGNORE INTO subjects (code, name, lecturer_id, created_at)
                                VALUES (?, ?, ?, ?)
                            """, (
                                subject["code"],
                                subject["name"],
                                lecturer_id,
                                now
                            ))
                            print(f"   ✅ Assigned subject: {subject['code']} - {subject['name']}")
                        except sqlite3.Error as e:
                            print(f"   ❌ Failed to assign subject {subject['code']}: {e}")
                
                else:
                    print(f"⚠️  Lecturer already exists: {lecturer['username']}")
                    lecturer_id = existing_user[0]
                    
            except sqlite3.Error as e:
                print(f"❌ Failed to create lecturer {lecturer['username']}: {e}")
                continue

        print("💾 INIT_DB: Committing changes...")
        conn.commit()

        # Verify tables exist
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [t[0] for t in c.fetchall()]
        print(f"✅ INIT_DB: Tables present: {tables}")

        conn.close()
        print("🔐 INIT_DB: Database connection closed")

    except Exception as e:
        print(f"❌ INIT_DB ERROR: {e}")
        import traceback
        traceback.print_exc()
        if 'conn' in locals():
            conn.close()


def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()

def now_iso():
    return datetime.datetime.utcnow().isoformat() + "Z"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 LIFESPAN: Starting up application...")
    print(f"🗃️ LIFESPAN: Database path: {DB_PATH}")
    init_db()
    print("✅ LIFESPAN: Database initialized")
    yield
    # Shutdown (nothing needed for now)
    print("🛑 LIFESPAN: Shutting down application...")

app = FastAPI(title="Automark API", version="0.2.0", lifespan=lifespan)

# Force database initialization if lifespan isn't working
import atexit
init_db()
atexit.register(lambda: None)  # Cleanup on exit

# Mount static folder
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# CORS for dev (relax now, tighten later)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # during dev; later restrict to your file server / domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    username: str  # username or email (frontend can pass either)
    password: str
    remember_me: bool = False

class LoginOut(BaseModel):
    success: bool
    message: str
    token: str | None = None
    user: dict | None = None

class FolderCreate(BaseModel):
    name: str
    description: Optional[str] = None
    due_date: Optional[str] = None
    max_points: int = 100
    status: str = "draft"
    student_ids: List[int] = []

class FolderUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[str] = None
    max_points: Optional[int] = None
    status: Optional[str] = None
    student_ids: Optional[List[int]] = None

class GradeSubmission(BaseModel):
    score: int
    feedback: Optional[str] = None

class SubmissionReceive(BaseModel):
    folder_id: int
    content: Optional[str] = None  # optional payload; extend later for uploads

class SubjectCreate(BaseModel):
    code: str
    name: str
    lecturer_id: int

class SubjectEnrollment(BaseModel):
    student_id: int
    subject_id: int
    semester: str  # 'AUT' or 'SPR'
    year: int = 2025

class EnrollmentCreate(BaseModel):
    subject_code: str
    semester: str  # 'AUT' or 'SPR'
    year: int = 2025

class AssignmentTemplateCreate(BaseModel):
    subject_id: int
    name: str
    description: Optional[str] = None
    semester: str  # 'AUT' or 'SPR'
    year: int = 2025
    assignment_number: int
    due_date: Optional[str] = None
    max_points: int = 100
    template_files: Optional[Dict] = None  # JSON structure of template files

class AssignmentTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[str] = None
    max_points: Optional[int] = None
    status: Optional[str] = None
    template_files: Optional[Dict] = None

@app.get("/")
async def serverIndex():
    return FileResponse(STATIC_DIR / "login&register.html")
# def read_root():
#     return {"message": "Hello, Automark!"}

@app.get("/studentdash.html")
def student_dashboard():
    return FileResponse(STATIC_DIR / "studentdash.html")

@app.get("/lecturer-dashboard.html")
def lecturer_dashboard():
    return FileResponse(STATIC_DIR / "lecturer-dashboard.html")

@app.get("/databaseview.html")
def database_view():
    return FileResponse(STATIC_DIR / "databaseview.html")

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "automark", "version": "0.2.0"}

@app.get("/api/v1/ping")
def ping():
    return {"pong": True}

@app.get("/api/v1/users/public")
async def get_all_users_public():
    """Get all registered users (public access - read only)"""
    print(f"Connecting to database at: {DB_PATH}")
    from pathlib import Path
    print(f"Database exists: {Path(DB_PATH).exists()}")
    
    conn = sqlite3.connect(str(DB_PATH))  # Convert Path to string
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute("""
        SELECT id, username, email, role, first_name, last_name, 
               is_active, created_at, last_login 
        FROM users 
        ORDER BY created_at DESC
    """)
    users = c.fetchall()
    conn.close()
    
    print(f"Found {len(users)} users in database")
    return [dict(user) for user in users]

@app.post("/api/v1/auth/register", response_model=RegisterOut)
def register(body: RegisterIn):
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
    
    # Create SSH user automatically
    try:
        ssh_result = create_ssh_user_for_registration(body.username.strip(), body.password)
        if ssh_result["success"]:
            logger.info(f"SSH user created for {body.username}: {ssh_result['message']}")
        else:
            logger.warning(f"SSH user creation failed for {body.username}: {ssh_result.get('error', 'Unknown error')}")
            # Note: We don't fail the registration if SSH creation fails
            # The user can still use the web interface
    except Exception as e:
        logger.error(f"Error creating SSH user for {body.username}: {e}")
        # Continue with registration even if SSH creation fails
    
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

def _set_submission_status(submission_id: int, status: str, feedback: Optional[str] = None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if feedback is not None:
        c.execute(
            "UPDATE submissions SET status = ?, feedback = ? WHERE id = ?",
            (status, feedback, submission_id),
        )
    else:
        c.execute(
            "UPDATE submissions SET status = ? WHERE id = ?",
            (status, submission_id),
        )
    conn.commit()
    conn.close()


def _set_submission_score(submission_id: int, score: int):
    """Optional helper to persist numeric score + graded_at."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "UPDATE submissions SET score = ?, graded_at = ? WHERE id = ?",
        (score, now_iso(), submission_id),
    )
    conn.commit()
    conn.close()


def _run_submission_job(submission_id: int, env_extra: Optional[dict] = None):
    """
    Launch a sandbox container if Docker SDK + socket are available; otherwise simulate.
    Status transitions: queued -> running -> completed/failed.
    """
    try:
        _set_submission_status(submission_id, "running")

        # Simulated path when Docker isn't available inside API
        if docker is None or not os.path.exists("/var/run/docker.sock"):
            time.sleep(1.0)
            _set_submission_status(submission_id, "completed", feedback='{"simulated": true}')
            return

        client = docker.from_env()
        env = {"SUBMISSION_ID": str(submission_id)}
        if env_extra:
            env.update(env_extra)

        name = f"automark-sbx-{submission_id}-{uuid.uuid4().hex[:8]}"
        container = None
        try:
            container = client.containers.run(
                "automark-sandbox:latest",
                command=["python", "/work/run.py"],  # ensure run.py actually runs
                name=name,
                environment=env,

                # ---- isolation/limits ----
                network_disabled=True,
                read_only=True,
                mem_limit="512m",
                nano_cpus=1_000_000_000,   # 1 CPU
                pids_limit=256,
                security_opt=["no-new-privileges"],
                cap_drop=["ALL"],
                tmpfs={"/tmp": "", "/run": ""},
                working_dir="/work",
                user="runner",
                # ---------------------------

                detach=True,
                auto_remove=False,          # fetch logs first, then remove
            )

            # Wait for exit, then read logs
            exit_info = container.wait()   # blocks until finished
            code = exit_info.get("StatusCode", 1) if isinstance(exit_info, dict) else int(exit_info)
            try:
                raw = container.logs(stdout=True, stderr=True, tail=2000)
                logs = raw.decode("utf-8", "ignore") if isinstance(raw, (bytes, bytearray)) else str(raw)
            except Exception as log_err:
                logs = f"[no logs available: {log_err}]"

        except Exception as e:
            code = 1
            logs = f"runner error: {e}"
        finally:
            if container is not None:
                try:
                    container.remove(force=True)  # remove AFTER grabbing logs
                except Exception:
                    pass

        # --- Parse structured JSON from the runner if present ---
        # Default based on exit code
        status = "completed" if code == 0 else "failed"
        fb = (logs or "")[-4000:]
        score = None

        import json
        try:
            last_line = fb.strip().splitlines()[-1]
            obj = json.loads(last_line)
            if isinstance(obj, dict):
                # Prefer explicit ok/status if provided by the runner
                if "ok" in obj:
                    status = "completed" if bool(obj["ok"]) else "failed"
                elif obj.get("status") in ("completed", "failed"):
                    status = obj["status"]

                if "score" in obj and obj["score"] is not None:
                    score = int(obj["score"])

                # Keep compact JSON as feedback for UI/logs
                fb = json.dumps(obj, ensure_ascii=False)
        except Exception:
            # If parsing fails, fall back to exit code + raw logs
            pass

        _set_submission_status(submission_id, status, feedback=fb)
        if score is not None:
            _set_submission_score(submission_id, score)

    except Exception as e:
        _set_submission_status(
            submission_id,
            "failed",
            feedback=f"runner error: {e}\n{traceback.format_exc()}",
        )



from fastapi import Header

# --- Session validation (helper + route) ---
def _validate_session(token: str):
    """Core session validation logic used by both the route and Depends()"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        now = datetime.datetime.utcnow().isoformat() + "Z"
        c.execute("""
            SELECT s.token, s.is_active as session_active, s.expires_at, 
                   u.id, u.username, u.email, u.role, u.first_name, u.last_name, u.is_active as user_active
            FROM sessions s 
            JOIN users u ON u.id = s.user_id 
            WHERE s.token = ?
        """, (token,))
        row = c.fetchone()
        if not row:
            return {"valid": False, "message": "Invalid session"}

        d = dict(row)
        if (d["session_active"] != 1 or d["user_active"] != 1 or now > d["expires_at"]):
            return {"valid": False, "message": "Session expired or inactive"}

        return {
            "valid": True,
            "user": {
                "id": d["id"],
                "username": d["username"],
                "email": d["email"],
                "role": d["role"],
                "firstName": d["first_name"],
                "lastName": d["last_name"],
            },
        }
    finally:
        conn.close()

@app.get("/api/v1/auth/session/{token}")
def validate_session(token: str):
    """Public route to validate a session (kept for the frontend / debugging)"""
    return _validate_session(token)


async def get_current_user(request: Request):
    """Get current user from session token"""
    auth_header = request.headers.get("Authorization")
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
    else:
        token = request.query_params.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")

    result = _validate_session(token)  # <-- use helper, not the route fn
    if not result["valid"]:
        raise HTTPException(status_code=401, detail=result["message"])
    return result["user"]


# Folders endpoints
@app.get("/api/v1/folders")
async def get_lecturer_folders(current_user: dict = Depends(get_current_user)):
    """Get all folders created by the current lecturer"""
    if current_user["role"] != "lecturer":
        raise HTTPException(status_code=403, detail="Only lecturers can access folders")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    try:
        # Get folders with assigned student count
        c.execute("""
            SELECT f.*, COUNT(fa.student_id) as assigned_students_count
            FROM folders f
            LEFT JOIN folder_assignments fa ON f.id = fa.folder_id
            WHERE f.lecturer_id = ?
            GROUP BY f.id
            ORDER BY f.created_at DESC
        """, (current_user["id"],))
        
        folders = c.fetchall()
        return [dict(folder) for folder in folders]
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()

@app.post("/api/v1/folders")
async def create_folder(folder: FolderCreate, current_user: dict = Depends(get_current_user)):
    """Create a new assignment folder"""
    if current_user["role"] != "lecturer":
        raise HTTPException(status_code=403, detail="Only lecturers can create folders")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        now = now_iso()
        c.execute("""
            INSERT INTO folders (name, description, due_date, max_points, status, created_at, updated_at, lecturer_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            folder.name,
            folder.description,
            folder.due_date,
            folder.max_points,
            folder.status,
            now,
            now,
            current_user["id"],
        ))
        folder_id = c.lastrowid

        # Assign students (if any)
        assigned = 0
        if folder.student_ids:
            for student_id in folder.student_ids:
                c.execute("""
                    INSERT OR IGNORE INTO folder_assignments (folder_id, student_id, assigned_at)
                    VALUES (?, ?, ?)
                """, (folder_id, student_id, now))
                assigned += 1

        conn.commit()

        # Return the inserted object directly (avoid SELECT that was erroring)
        return {
            "id": folder_id,
            "name": folder.name,
            "description": folder.description,
            "due_date": folder.due_date,
            "max_points": folder.max_points,
            "status": folder.status,
            "created_at": now,
            "updated_at": now,
            "lecturer_id": current_user["id"],
            "assigned_students_count": assigned,
        }

    except sqlite3.Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()


@app.put("/api/v1/folders/{folder_id}")
async def update_folder(folder_id: int, folder: FolderUpdate, current_user: dict = Depends(get_current_user)):
    """Update a folder"""
    if current_user["role"] != "lecturer":
        raise HTTPException(status_code=403, detail="Only lecturers can update folders")
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    try:
        # Verify folder belongs to current lecturer
        c.execute("SELECT lecturer_id FROM folders WHERE id = ?", (folder_id,))
        result = c.fetchone()
        if not result or result[0] != current_user["id"]:
            raise HTTPException(status_code=404, detail="Folder not found")
        
        # Build update query dynamically
        update_fields = []
        update_values = []
        
        if folder.name is not None:
            update_fields.append("name = ?")
            update_values.append(folder.name)
        if folder.description is not None:
            update_fields.append("description = ?")
            update_values.append(folder.description)
        if folder.due_date is not None:
            update_fields.append("due_date = ?")
            update_values.append(folder.due_date)
        if folder.max_points is not None:
            update_fields.append("max_points = ?")
            update_values.append(folder.max_points)
        if folder.status is not None:
            update_fields.append("status = ?")
            update_values.append(folder.status)
        
        update_fields.append("updated_at = ?")
        update_values.append(now_iso())
        
        if update_fields:
            update_values.append(folder_id)
            c.execute(f"UPDATE folders SET {', '.join(update_fields)} WHERE id = ?", update_values)
        
        # Update student assignments if provided
        if folder.student_ids is not None:
            # Remove existing assignments
            c.execute("DELETE FROM folder_assignments WHERE folder_id = ?", (folder_id,))
            
            # Add new assignments
            now = now_iso()
            for student_id in folder.student_ids:
                c.execute("""
                    INSERT INTO folder_assignments (folder_id, student_id, assigned_at)
                    VALUES (?, ?, ?)
                """, (folder_id, student_id, now))
        
        conn.commit()
        
        # Return updated folder
        c.execute("""
            SELECT f.*, COUNT(fa.student_id) as assigned_students_count
            FROM folders f
            LEFT JOIN folder_assignments fa ON f.id = fa.folder_id
            WHERE f.id = ?
            GROUP BY f.id
        """, (folder_id,))
        
        updated_folder = dict(c.fetchone())
        return updated_folder
        
    except sqlite3.Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()

@app.delete("/api/v1/folders/{folder_id}")
async def delete_folder(folder_id: int, current_user: dict = Depends(get_current_user)):
    """Delete a folder and its assignments"""
    if current_user["role"] != "lecturer":
        raise HTTPException(status_code=403, detail="Only lecturers can delete folders")
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    try:
        # Verify folder belongs to current lecturer
        c.execute("SELECT lecturer_id FROM folders WHERE id = ?", (folder_id,))
        result = c.fetchone()
        if not result or result[0] != current_user["id"]:
            raise HTTPException(status_code=404, detail="Folder not found")
        
        # Delete folder assignments first (foreign key constraint)
        c.execute("DELETE FROM folder_assignments WHERE folder_id = ?", (folder_id,))
        
        # Delete folder
        c.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
        
        conn.commit()
        return {"message": "Folder deleted successfully"}
        
    except sqlite3.Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()

# Students endpoints
@app.get("/api/v1/students")
async def get_all_students(current_user: dict = Depends(get_current_user)):
    """Get all students (for lecturers only)"""
    if current_user["role"] != "lecturer":
        raise HTTPException(status_code=403, detail="Only lecturers can access student list")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    try:
        c.execute("""
            SELECT id, username, email, first_name, last_name, created_at
            FROM users 
            WHERE role = 'student' AND is_active = 1
            ORDER BY first_name, last_name
        """)
        
        students = c.fetchall()
        return [dict(student) for student in students]
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()

# Submissions endpoints
@app.get("/api/v1/submissions")
async def get_submissions(current_user: dict = Depends(get_current_user)):
    """Get all submissions for lecturer's folders"""
    if current_user["role"] != "lecturer":
        raise HTTPException(status_code=403, detail="Only lecturers can access submissions")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    try:
        c.execute("""
            SELECT s.*, f.name as folder_name, u.first_name, u.last_name, u.username
            FROM submissions s
            JOIN folders f ON s.folder_id = f.id
            JOIN users u ON s.student_id = u.id
            WHERE f.lecturer_id = ?
            ORDER BY s.submitted_at DESC
        """, (current_user["id"],))
        
        submissions = c.fetchall()
        return [dict(sub) for sub in submissions]
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()

@app.post("/api/v1/submissions/{submission_id}/grade")
async def grade_submission(submission_id: int, grade: GradeSubmission, current_user: dict = Depends(get_current_user)):
    """Grade a submission"""
    if current_user["role"] != "lecturer":
        raise HTTPException(status_code=403, detail="Only lecturers can grade submissions")
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    try:
        # Verify submission belongs to lecturer's folder
        c.execute("""
            SELECT s.id 
            FROM submissions s
            JOIN folders f ON s.folder_id = f.id
            WHERE s.id = ? AND f.lecturer_id = ?
        """, (submission_id, current_user["id"]))
        
        if not c.fetchone():
            raise HTTPException(status_code=404, detail="Submission not found")
        
        # Update submission with grade
        c.execute("""
            UPDATE submissions 
            SET score = ?, feedback = ?, status = 'graded', graded_at = ?
            WHERE id = ?
        """, (grade.score, grade.feedback, now_iso(), submission_id))
        
        conn.commit()
        return {"message": "Submission graded successfully"}
        
    except sqlite3.Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()

# SSH User Management Endpoints (Admin)
@app.get("/api/v1/admin/ssh-users")
def list_ssh_users():
    """List all SSH users in the container"""
    try:
        from ssh_user_manager import SSHUserManager
        manager = SSHUserManager()
        result = manager.list_users()
        return result
    except Exception as e:
        logger.error(f"Error listing SSH users: {e}")
        raise HTTPException(500, f"Failed to list SSH users: {str(e)}")

@app.post("/api/v1/admin/ssh-users/{username}")
def create_ssh_user_admin(username: str, password: str):
    """Manually create SSH user (admin endpoint)"""
    try:
        result = create_ssh_user_for_registration(username, password)
        if not result["success"]:
            raise HTTPException(400, result.get("error", "Failed to create SSH user"))
        return result
    except Exception as e:
        logger.error(f"Error creating SSH user {username}: {e}")
        raise HTTPException(500, f"Failed to create SSH user: {str(e)}")

@app.delete("/api/v1/admin/ssh-users/{username}")
def delete_ssh_user_admin(username: str):
    """Delete SSH user (admin endpoint)"""
    try:
        from ssh_user_manager import SSHUserManager
        manager = SSHUserManager()
        result = manager.delete_user(username)
        if not result["success"]:
            raise HTTPException(400, result.get("error", "Failed to delete SSH user"))
        return result
    except Exception as e:
        logger.error(f"Error deleting SSH user {username}: {e}")
        raise HTTPException(500, f"Failed to delete SSH user: {str(e)}")

# Submissions: receive + poll
@app.post("/api/v1/submissions/receive")
def receive_submission(body: SubmissionReceive, current_user: dict = Depends(get_current_user)):
    """Student submits to a folder -> enqueue sandbox run (in a background thread)."""
    if current_user["role"] != "student":
        raise HTTPException(403, "Only students can submit")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        # ensure folder exists
        c.execute("SELECT id FROM folders WHERE id = ?", (body.folder_id,))
        if not c.fetchone():
            raise HTTPException(404, "Folder not found")
        now = now_iso()
        c.execute("""
            INSERT INTO submissions (folder_id, student_id, submitted_at, status, feedback)
            VALUES (?, ?, ?, ?, ?)
        """, (body.folder_id, current_user["id"], now, "queued", body.content or ""))
        sid = c.lastrowid
        conn.commit()
    finally:
        conn.close()
    threading.Thread(target=_run_submission_job, args=(sid,), daemon=True).start()
    return {"submission_id": sid, "status": "queued"}

@app.get("/api/v1/submissions/{submission_id}")
def get_submission(submission_id: int, current_user: dict = Depends(get_current_user)):
    """Poll submission status. Students see their own; lecturers see their students'."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM submissions WHERE id = ?", (submission_id,))
        row = c.fetchone()
        if not row:
            raise HTTPException(404, "Submission not found")
        sub = dict(row)
        if current_user["role"] == "student" and sub["student_id"] != current_user["id"]:
            raise HTTPException(403, "Forbidden")
        if current_user["role"] == "lecturer":
            c.execute("SELECT lecturer_id FROM folders WHERE id = ?", (sub["folder_id"],))
            owner = c.fetchone()
            if not owner or owner[0] != current_user["id"]:
                raise HTTPException(403, "Forbidden")
        return sub
    finally:
        conn.close()

# API endpoints for assignment templates
@app.get("/api/v1/assignment-templates")
async def get_assignment_templates(current_user: dict = Depends(get_current_user)):
    """Get assignment templates for current lecturer"""
    if current_user["role"] != "lecturer":
        raise HTTPException(status_code=403, detail="Only lecturers can view assignment templates")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    try:
        c.execute("""
            SELECT at.*, s.code as subject_code, s.name as subject_name
            FROM assignment_templates at
            JOIN subjects s ON at.subject_id = s.id
            WHERE s.lecturer_id = ?
            ORDER BY at.year DESC, at.semester, s.code, at.assignment_number
        """, (current_user["id"],))
        
        templates = c.fetchall()
        return [dict(template) for template in templates]
        
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()

@app.post("/api/v1/assignment-templates")
async def create_assignment_template(template: AssignmentTemplateCreate, current_user: dict = Depends(get_current_user)):
    """Create a new assignment template"""
    if current_user["role"] != "lecturer":
        raise HTTPException(status_code=403, detail="Only lecturers can create assignment templates")
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    try:
        # Verify lecturer teaches this subject
        c.execute("SELECT lecturer_id FROM subjects WHERE id = ?", (template.subject_id,))
        subject_result = c.fetchone()
        if not subject_result or subject_result[0] != current_user["id"]:
            raise HTTPException(status_code=403, detail="You don't teach this subject")
        
        # Get subject info
        c.execute("SELECT code, name FROM subjects WHERE id = ?", (template.subject_id,))
        subject_info = c.fetchone()
        subject_code, subject_name = subject_info
        
        # Generate SVN path
        svn_path = f"templates/{template.year}-{template.semester}-{subject_code}-Assignment{template.assignment_number}"
        
        # Create template
        now = now_iso()
        c.execute("""
            INSERT INTO assignment_templates 
            (subject_id, name, description, semester, year, assignment_number, template_files, 
             svn_path, due_date, max_points, status, created_at, updated_at, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?)
        """, (
            template.subject_id,
            template.name,
            template.description,
            template.semester,
            template.year,
            template.assignment_number,
            json.dumps(template.template_files) if template.template_files else None,
            svn_path,
            template.due_date,
            template.max_points,
            now,
            now,
            current_user["id"]
        ))
        
        template_id = c.lastrowid
        conn.commit()
        
        # Trigger SVN template creation
        svn_success = False
        try:
            svn_success = create_svn_template(svn_path, template.name, template.template_files or {})
        except Exception as e:
            logger.warning(f"Failed to create SVN template: {e}")
        
        # Auto-update SSH directories for all enrolled students
        students_updated = 0
        if svn_success:
            # Get all students enrolled in this subject for this semester/year
            c.execute("""
                SELECT DISTINCT u.username
                FROM subject_enrollments se
                JOIN users u ON se.student_id = u.id
                WHERE se.subject_id = ? AND se.semester = ? AND se.year = ? AND se.status = 'active'
            """, (template.subject_id, template.semester, template.year))
            
            enrolled_students = c.fetchall()
            
            # Update SSH directories and create submission repos for each enrolled student
            from ssh_user_manager import update_user_directories, create_student_submission_repo
            assignment_path = f"{template.year}-{template.semester}-{subject_code}-Assignment{template.assignment_number}"
            
            for (username,) in enrolled_students:
                try:
                    # Update SSH directories
                    result = update_user_directories(username)
                    if result.get("success"):
                        students_updated += 1
                        logger.info(f"Updated SSH directories for {username} after creating assignment template")
                    else:
                        logger.warning(f"Failed to update SSH directories for {username}: {result.get('error', 'Unknown error')}")
                    
                    # Create student submission repository for this new assignment
                    repo_result = create_student_submission_repo(username, assignment_path)
                    if repo_result["success"]:
                        logger.info(f"Created submission repo for {username}: {assignment_path}")
                    else:
                        logger.warning(f"Failed to create submission repo for {username}: {repo_result.get('error')}")
                        
                except Exception as e:
                    logger.error(f"Error updating directories/repos for {username}: {e}")
        
        message = "Assignment template created successfully"
        if not svn_success:
            message += " (SVN template creation failed - check logs)"
        if students_updated > 0:
            message += f" SSH directories updated for {students_updated} enrolled students."
        
        return {
            "id": template_id, 
            "svn_path": svn_path, 
            "svn_created": svn_success,
            "students_updated": students_updated,
            "message": message
        }
        
    except sqlite3.IntegrityError:
        conn.rollback()
        raise HTTPException(status_code=409, detail="Assignment template already exists for this subject/semester/assignment number")
    except sqlite3.Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()

def create_svn_template(svn_path: str, name: str, template_files: Dict):
    """Create SVN template structure by communicating with SVN container"""
    import subprocess
    import tempfile
    import shutil
    
    logger.info(f"Creating SVN template at {svn_path} with name '{name}'")
    
    try:
        # Create temporary working directory
        with tempfile.TemporaryDirectory() as temp_dir:
            # Checkout the SVN repository 
            checkout_cmd = [
                "docker", "exec", "automark-svn", 
                "svn", "checkout", "file:///var/svn/repositories/automark", "/tmp/svn-work", "--force"
            ]
            result = subprocess.run(checkout_cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                logger.error(f"SVN checkout failed: {result.stderr}")
                return False
            
            # Create template directory structure
            template_dir = f"/tmp/svn-work/{svn_path}"
            mkdir_cmd = [
                "docker", "exec", "automark-svn",
                "mkdir", "-p", template_dir
            ]
            result = subprocess.run(mkdir_cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                logger.error(f"Failed to create template directory: {result.stderr}")
                return False
            
            # Create default template structure if no template_files provided
            if not template_files:
                template_files = create_default_template_structure(name)
            
            # Create each file in the template
            for file_path, content in template_files.items():
                full_path = f"{template_dir}/{file_path}"
                
                # Create directory if needed
                dir_path = "/".join(full_path.split("/")[:-1])
                if dir_path != template_dir:
                    mkdir_cmd = [
                        "docker", "exec", "automark-svn",
                        "mkdir", "-p", dir_path
                    ]
                    subprocess.run(mkdir_cmd, capture_output=True, text=True, timeout=10)
                
                # Create file content
                create_file_cmd = [
                    "docker", "exec", "automark-svn",
                    "bash", "-c", f"cat > {full_path} << 'TEMPLATE_EOF'\n{content}\nTEMPLATE_EOF"
                ]
                result = subprocess.run(create_file_cmd, capture_output=True, text=True, timeout=15)
                
                if result.returncode != 0:
                    logger.error(f"Failed to create file {file_path}: {result.stderr}")
            
            # Add files to SVN
            svn_add_cmd = [
                "docker", "exec", "automark-svn",
                "bash", "-c", f"cd /tmp/svn-work && svn add {svn_path} --force"
            ]
            result = subprocess.run(svn_add_cmd, capture_output=True, text=True, timeout=20)
            
            if result.returncode != 0:
                logger.error(f"SVN add failed: {result.stderr}")
                return False
            
            # Commit the template
            commit_cmd = [
                "docker", "exec", "automark-svn",
                "bash", "-c", f"cd /tmp/svn-work && svn commit -m 'Create assignment template: {name}' --username admin --password adminpass123 --no-auth-cache"
            ]
            result = subprocess.run(commit_cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                logger.error(f"SVN commit failed: {result.stderr}")
                return False
            
            # Cleanup
            cleanup_cmd = [
                "docker", "exec", "automark-svn",
                "rm", "-rf", "/tmp/svn-work"
            ]
            subprocess.run(cleanup_cmd, capture_output=True, text=True, timeout=10)
            
            logger.info(f"✅ Successfully created SVN template: {svn_path}")
            return True
            
    except subprocess.TimeoutExpired:
        logger.error("SVN template creation timed out")
        return False
    except Exception as e:
        logger.error(f"Error creating SVN template: {e}")
        return False

def create_default_template_structure(assignment_name: str) -> Dict[str, str]:
    """Create default template files for an assignment"""
    
    # Determine assignment type from name for better defaults
    is_database = "database" in assignment_name.lower() or "sql" in assignment_name.lower()
    is_programming = "programming" in assignment_name.lower() or "code" in assignment_name.lower()
    is_oop = "oop" in assignment_name.lower() or "object" in assignment_name.lower()
    
    template_files = {}
    
    # Always create README
    template_files["README.md"] = f"""# {assignment_name}

## Overview
This assignment focuses on [assignment objectives].

## Files to Complete
- See the source files in the `src/` directory
- Complete the implementation according to the requirements
- Run tests to verify your solution

## Testing
Run the test suite with:
```bash
python -m pytest tests/
```

## Submission
Commit your work using SVN:
```bash
svn add .
svn commit -m "Assignment submission"
```

## Due Date
Please check the course website for the official due date.

## Requirements
- Follow coding standards and best practices
- Include proper documentation
- Ensure all tests pass before submission
"""
    
    if is_database:
        # Database assignment template
        template_files["src/database.py"] = '''"""
Assignment: Database Implementation
Student: [Your Name]
Student ID: [Your Student ID]

Complete the functions below to implement the required database operations.
"""

import sqlite3
from typing import List, Dict, Any, Optional

def connect_database(db_path: str) -> sqlite3.Connection:
    """
    Create a connection to the SQLite database.
    
    Args:
        db_path: Path to the SQLite database file
        
    Returns:
        sqlite3.Connection object
    """
    # TODO: Implement database connection
    pass

def create_tables(conn: sqlite3.Connection) -> None:
    """
    Create the required tables for this assignment.
    
    Args:
        conn: Database connection object
    """
    # TODO: Implement table creation
    pass

def execute_query(conn: sqlite3.Connection, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
    """
    Execute a SELECT query and return results as list of dictionaries.
    
    Args:
        conn: Database connection object
        query: SQL query string
        params: Query parameters
        
    Returns:
        List of dictionaries containing query results
    """
    # TODO: Implement query execution
    pass
'''

        template_files["src/queries.sql"] = f'''-- {assignment_name}
-- Student: [Your Name]
-- Student ID: [Your Student ID]

-- Query 1: Create table(s)
-- TODO: Write CREATE TABLE statement(s)

-- Query 2: Insert sample data
-- TODO: Write INSERT statement(s)

-- Query 3: Basic SELECT query
-- TODO: Write SELECT statement

-- Query 4: JOIN query
-- TODO: Write SELECT statement with JOIN

-- Query 5: Aggregate query
-- TODO: Write SELECT statement with GROUP BY/aggregation
'''

        template_files["tests/test_database.py"] = '''"""
Test suite for Database Assignment
"""

import pytest
import sqlite3
import tempfile
import os
from src.database import connect_database, create_tables, execute_query

@pytest.fixture
def temp_db():
    """Create a temporary database for testing"""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    os.unlink(path)

def test_database_connection(temp_db):
    """Test that database connection works"""
    conn = connect_database(temp_db)
    assert isinstance(conn, sqlite3.Connection)
    conn.close()

def test_table_creation(temp_db):
    """Test that tables are created correctly"""
    conn = connect_database(temp_db)
    create_tables(conn)
    
    # Check that tables exist
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    
    # TODO: Add assertions for expected tables
    assert len(tables) > 0, "No tables were created"
    conn.close()

# TODO: Add more specific tests for your implementation
'''

    elif is_oop or is_programming:
        # Programming/OOP assignment template
        template_files["src/main.py"] = f'''"""
{assignment_name}
Student: [Your Name]
Student ID: [Your Student ID]

Implement the required classes and functions below.
"""

class BaseClass:
    """
    Base class for the assignment.
    """
    
    def __init__(self):
        # TODO: Implement initialization
        pass
    
    def method_example(self):
        """
        Example method to implement.
        """
        # TODO: Implement this method
        pass

# TODO: Add more classes and functions as required
'''

        template_files["tests/test_main.py"] = '''"""
Test suite for Programming Assignment
"""

import pytest
from src.main import BaseClass

def test_base_class_creation():
    """Test that BaseClass can be instantiated"""
    obj = BaseClass()
    assert obj is not None

def test_method_example():
    """Test the example method"""
    obj = BaseClass()
    # TODO: Add specific tests for your implementation
    assert hasattr(obj, 'method_example')

# TODO: Add more specific tests
'''

    else:
        # Generic assignment template
        template_files["src/solution.py"] = f'''"""
{assignment_name}
Student: [Your Name]
Student ID: [Your Student ID]

Implement your solution below.
"""

def main():
    """
    Main function for the assignment.
    """
    # TODO: Implement your solution here
    pass

if __name__ == "__main__":
    main()
'''

        template_files["tests/test_solution.py"] = '''"""
Test suite for Assignment
"""

import pytest
from src.solution import main

def test_main_function():
    """Test that main function exists and runs"""
    # TODO: Add specific tests for your implementation
    assert callable(main)

# TODO: Add more specific tests
'''
    
    # Always add a requirements.txt for Python dependencies
    template_files["requirements.txt"] = """# Add any required Python packages here
pytest>=7.0.0
# Add other dependencies as needed
"""
    
    # Add .gitignore equivalent for SVN
    template_files[".svnignore"] = """*.pyc
__pycache__/
*.pyo
*.pyd
.Python
*.so
.pytest_cache/
*.log
.DS_Store
"""
    
    return template_files

# API endpoints for subject enrollments
@app.post("/api/v1/enrollments")
async def enroll_student(enrollment: EnrollmentCreate, current_user: dict = Depends(get_current_user)):
    """Enroll current user (student) in a subject"""
    if current_user["role"] != "student":
        raise HTTPException(status_code=403, detail="Only students can enroll in subjects")
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    try:
        # Find subject by code
        c.execute("SELECT id FROM subjects WHERE code = ?", (enrollment.subject_code,))
        subject_result = c.fetchone()
        if not subject_result:
            raise HTTPException(status_code=404, detail="Subject not found")
        
        subject_id = subject_result[0]
        
        # Check if already enrolled
        c.execute("""
            SELECT id FROM subject_enrollments 
            WHERE student_id = ? AND subject_id = ? AND semester = ? AND year = ?
        """, (current_user["id"], subject_id, enrollment.semester, enrollment.year))
        
        if c.fetchone():
            raise HTTPException(status_code=409, detail="Already enrolled in this subject for this semester")
        
        # Enroll student
        c.execute("""
            INSERT INTO subject_enrollments (student_id, subject_id, enrolled_at, semester, year, status)
            VALUES (?, ?, ?, ?, ?, 'active')
        """, (current_user["id"], subject_id, now_iso(), enrollment.semester, enrollment.year))
        
        conn.commit()
        
        # Trigger SSH directory creation for this enrollment
        try:
            from ssh_user_manager import update_user_directories
            update_result = update_user_directories(current_user["username"])
            if not update_result["success"]:
                logger.warning(f"Failed to update SSH directories for {current_user['username']}: {update_result.get('error')}")
        except Exception as e:
            logger.error(f"Error updating SSH directories for {current_user['username']}: {e}")
        
        # Create student submission repositories for existing assignments in this subject
        try:
            from ssh_user_manager import create_student_submission_repo
            
            # Get existing assignment templates for this subject/semester/year
            c.execute("""
                SELECT at.assignment_number, at.name, s.code
                FROM assignment_templates at
                JOIN subjects s ON at.subject_id = s.id
                WHERE at.subject_id = ? AND at.semester = ? AND at.year = ? AND at.status IN ('draft', 'published')
            """, (subject_id, enrollment.semester, enrollment.year))
            
            existing_assignments = c.fetchall()
            
            for assignment_number, assignment_name, subject_code in existing_assignments:
                assignment_path = f"{enrollment.year}-{enrollment.semester}-{subject_code}-Assignment{assignment_number}"
                repo_result = create_student_submission_repo(current_user["username"], assignment_path)
                if repo_result["success"]:
                    logger.info(f"Created submission repo for {current_user['username']}: {assignment_path}")
                else:
                    logger.warning(f"Failed to create submission repo for {current_user['username']}: {repo_result.get('error')}")
                    
        except Exception as e:
            logger.error(f"Error creating student submission repositories for {current_user['username']}: {e}")
        
        return {"message": f"Successfully enrolled in {enrollment.subject_code} for {enrollment.semester} {enrollment.year}"}
        
    except sqlite3.Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()

@app.get("/api/v1/enrollments/my")
async def get_my_enrollments(current_user: dict = Depends(get_current_user)):
    """Get current user's enrollments"""
    if current_user["role"] != "student":
        raise HTTPException(status_code=403, detail="Only students can view enrollments")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    try:
        c.execute("""
            SELECT se.*, s.code, s.name, u.first_name, u.last_name
            FROM subject_enrollments se
            JOIN subjects s ON se.subject_id = s.id
            JOIN users u ON s.lecturer_id = u.id
            WHERE se.student_id = ? AND se.status = 'active'
            ORDER BY se.year DESC, se.semester, s.code
        """, (current_user["id"],))
        
        enrollments = c.fetchall()
        return [dict(enrollment) for enrollment in enrollments]
        
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()

@app.get("/api/v1/subjects/{subject_id}/students")
async def get_subject_students(subject_id: int, current_user: dict = Depends(get_current_user)):
    """Get all students enrolled in a subject (lecturers only)"""
    if current_user["role"] != "lecturer":
        raise HTTPException(status_code=403, detail="Only lecturers can view subject enrollments")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    try:
        # Verify lecturer teaches this subject
        c.execute("SELECT lecturer_id FROM subjects WHERE id = ?", (subject_id,))
        subject_result = c.fetchone()
        if not subject_result or subject_result["lecturer_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="You don't teach this subject")
        
        # Get enrolled students
        c.execute("""
            SELECT se.*, u.username, u.email, u.first_name, u.last_name
            FROM subject_enrollments se
            JOIN users u ON se.student_id = u.id
            WHERE se.subject_id = ? AND se.status = 'active'
            ORDER BY se.semester, se.year, u.first_name, u.last_name
        """, (subject_id,))
        
        students = c.fetchall()
        return [dict(student) for student in students]
        
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()

@app.post("/api/v1/subjects/{subject_id}/enroll-student")
async def enroll_student_admin(subject_id: int, student_id: int, semester: str, year: int = 2025, 
                               current_user: dict = Depends(get_current_user)):
    """Enroll a student in a subject (lecturers only)"""
    if current_user["role"] != "lecturer":
        raise HTTPException(status_code=403, detail="Only lecturers can enroll students")
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    try:
        # Verify lecturer teaches this subject
        c.execute("SELECT lecturer_id FROM subjects WHERE id = ?", (subject_id,))
        subject_result = c.fetchone()
        if not subject_result or subject_result[0] != current_user["id"]:
            raise HTTPException(status_code=403, detail="You don't teach this subject")
        
        # Verify student exists
        c.execute("SELECT username FROM users WHERE id = ? AND role = 'student'", (student_id,))
        student_result = c.fetchone()
        if not student_result:
            raise HTTPException(status_code=404, detail="Student not found")
        
        # Check if already enrolled
        c.execute("""
            SELECT id FROM subject_enrollments 
            WHERE student_id = ? AND subject_id = ? AND semester = ? AND year = ?
        """, (student_id, subject_id, semester, year))
        
        if c.fetchone():
            raise HTTPException(status_code=409, detail="Student already enrolled")
        
        # Enroll student
        c.execute("""
            INSERT INTO subject_enrollments (student_id, subject_id, enrolled_at, semester, year, status)
            VALUES (?, ?, ?, ?, ?, 'active')
        """, (student_id, subject_id, now_iso(), semester, year))
        
        conn.commit()
        
        # Update SSH directories for enrolled student
        try:
            from ssh_user_manager import update_user_directories
            update_result = update_user_directories(student_result[0])
            if not update_result["success"]:
                logger.warning(f"Failed to update SSH directories for {student_result[0]}: {update_result.get('error')}")
        except Exception as e:
            logger.error(f"Error updating SSH directories for {student_result[0]}: {e}")
        
        return {"message": f"Successfully enrolled student in subject"}
        
    except sqlite3.Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()

# API endpoints for subjects
@app.get("/api/v1/subjects")
async def get_all_subjects(current_user: dict = Depends(get_current_user)):
    """Get all subjects"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    try:
        c.execute("""
            SELECT s.*, u.first_name, u.last_name 
            FROM subjects s
            JOIN users u ON s.lecturer_id = u.id
            ORDER BY s.code
        """)
        
        subjects = c.fetchall()
        return [dict(subject) for subject in subjects]
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()

@app.get("/api/v1/lecturers/{lecturer_id}/subjects")
async def get_lecturer_subjects(lecturer_id: int, current_user: dict = Depends(get_current_user)):
    """Get subjects assigned to a specific lecturer"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    try:
        c.execute("""
            SELECT s.* 
            FROM subjects s
            WHERE s.lecturer_id = ?
            ORDER BY s.code
        """, (lecturer_id,))
        
        subjects = c.fetchall()
        return [dict(subject) for subject in subjects]
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()

@app.get("/api/v1/subjects/{subject_code}")
async def get_subject(subject_code: str, current_user: dict = Depends(get_current_user)):
    """Get specific subject by code"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    try:
        c.execute("""
            SELECT s.*, u.first_name, u.last_name 
            FROM subjects s
            JOIN users u ON s.lecturer_id = u.id
            WHERE s.code = ?
        """, (subject_code,))
        
        subject = c.fetchone()
        if not subject:
            raise HTTPException(status_code=404, detail="Subject not found")
        
        return dict(subject)
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    finally:
        conn.close()
