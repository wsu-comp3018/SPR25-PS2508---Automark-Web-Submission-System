# Backend/server/app/main.py

from fastapi import FastAPI, HTTPException, Request, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager


from pydantic import BaseModel, EmailStr

import os
import json
import base64
import random
import hashlib
import sqlite3
import datetime
import logging
import threading
import time
import traceback
from pathlib import Path
from typing import List, Optional, Dict
import shutil
import zipfile
import uuid

# Local modules for SVN → sandbox flow (make sure these files exist under app/)
from . import storage, worker, docker_runner


# SSH user management (adjust path if this module lives elsewhere)
from ssh_user_manager import create_ssh_user_for_registration


# Database path
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "automark.db"))
STATIC_DIR = BASE_DIR / "static"
# print("STATIC_DIR exists?", STATIC_DIR.exists(), BASE_DIR)
# print("Files inside STATIC_DIR:", list(STATIC_DIR.rglob("*")))

# Remove duplicate import and DB_PATH redefinition
# sys.path.append('/app')
# from ssh_user_manager import create_ssh_user_for_registration
# DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "automark.db"))

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
                subject_code TEXT NOT NULL,
                FOREIGN KEY (lecturer_id) REFERENCES users(id),
                FOREIGN KEY (subject_code) REFERENCES subjects(code)
            )
        """)
        
        # Add migration for existing databases
        try:
            c.execute("ALTER TABLE folders ADD COLUMN subject_code TEXT")
            print("✅ Added subject_code column to folders table")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("✅ subject_code column already exists in folders table")
            else:
                print(f"⚠️ Migration warning: {e}")
        
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
                revisions INTEGER DEFAULT 1,
                file_ids TEXT,
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
        # NEW: add lecturer_file_ids column to folders if missing
        ensure_columns("folders", {
            "lecturer_file_ids": "TEXT"   # JSON array of file IDs (marker / reference files)
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
        
        print("📝 INIT_DB: Creating files table...")
        c.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                size INTEGER NOT NULL,
                content BLOB NOT NULL,
                uploaded_at TEXT NOT NULL,
                uploaded_by INTEGER NOT NULL,
                FOREIGN KEY (uploaded_by) REFERENCES users(id)
            )
        """)
        
        print("👨‍🎓 INIT_DB: Creating hardcoded students...")
        now = now_iso()
        students = [
                       {
                "username": "student_david",
                "email": "david.miller@student.automark.com",
                "password": "davidpass123",
                "first_name": "David",
                "last_name": "Miller",
                "subjects": ["COMP_0067", "COMP_0420"]
            },
            {
                "username": "student_emma",
                "email": "emma.jones@student.automark.com",
                "password": "emmapass123",
                "first_name": "Emma",
                "last_name": "Jones",
                "subjects": ["INFS_8586"]
            },
            {
                "username": "student_frank",
                "email": "frank.taylor@student.automark.com",
                "password": "frankpass123",
                "first_name": "Frank",
                "last_name": "Taylor",
                "subjects": ["COMP_5055", "INFS_8586"]
            }
        ]

        pending_student_subjects = []  # NEW: collect (username, [subject_codes]) to enroll after subjects exist

        for student in students:
            try:
                # Check if student already exists
                c.execute("SELECT id FROM users WHERE username = ?", (student["username"],))
                existing_user = c.fetchone()
                
                if not existing_user:
                    # Create student user
                    c.execute("""
                        INSERT INTO users (username, email, password_hash, role, first_name, last_name, created_at)
                        VALUES (?, ?, ?, 'student', ?, ?, ?)
                    """, (
                        student["username"],
                        student["email"],
                        hash_password(student["password"]),
                        student["first_name"],
                        student["last_name"],
                        now
                    ))
                    student_id = c.lastrowid
                    print(f"✅ Created student: {student['username']} (ID: {student_id})")
                    
                    # Create SSH user for student
                    try:
                        ssh_result = create_ssh_user_for_registration(student["username"], student["password"])
                        if ssh_result["success"]:
                            print(f"✅ Created SSH user for {student['username']}")
                        else:
                            print(f"⚠️  SSH user creation failed for {student['username']}: {ssh_result.get('error')}")
                    except Exception as e:
                        print(f"⚠️  SSH user creation error for {student['username']}: {e}")
                
                else:
                    print(f"⚠️  Student already exists: {student['username']}")
                # NEW: record desired subject enrollments (processed later after lecturer subjects are inserted)
                if student.get("subjects"):
                    pending_student_subjects.append((student["username"], student["subjects"]))
            except sqlite3.Error as e:
                print(f"❌ Failed to create student {student['username']}: {e}")
                continue

        print("💾 INIT_DB: Committing changes...")
        
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
                    {"code": "COMP_0067", "name": "Database and Design"}
                ]
            },
            {
                "username": "lecturer_prog",
                "email": "prog.lecturer@automark.com", 
                "password": "progpassword123",
                "first_name": "Sarah",
                "last_name": "Johnson",
                "subjects": [
                    {"code": "COMP_0420", "name": "Programming Techniques"}
                ]
            },
            {
                "username": "lecturer_oop",
                "email": "oop.lecturer@automark.com",
                "password": "ooppassword123", 
                "first_name": "Robert",
                "last_name": "Williams",
                "subjects": [
                    {"code": "INFS_8586", "name": "Object Oriented Programming"},
                    {"code": "COMP_5055", "name": "Software Engineering"}
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

        # NEW: enroll pre-provisioned students into specified subjects (after lecturers & subjects exist)
        try:
            semester, year = current_semester_year()
            for username, subj_codes in pending_student_subjects:
                c.execute("SELECT id FROM users WHERE username = ?", (username,))
                row = c.fetchone()
                if not row:
                    continue
                student_id = row[0]
                for code in subj_codes:
                    c.execute("SELECT id FROM subjects WHERE code = ?", (code,))
                    srow = c.fetchone()
                    if not srow:
                        print(f"   ⚠️ Cannot enroll {username}: subject {code} not found yet")
                        continue
                    subject_id = srow[0]
                    c.execute("""
                        INSERT OR IGNORE INTO subject_enrollments
                          (student_id, subject_id, enrolled_at, semester, year, status)
                        VALUES (?, ?, ?, ?, ?, 'active')
                    """, (student_id, subject_id, now_iso(), semester, year))
                    # Auto-assign existing folders for that subject
                    auto_assign_student_to_subject_folders(conn, student_id, subject_id)
            print("✅ Processed predefined student subject enrollments")
        except Exception as e:
            print(f"⚠️ Enrollment staging error: {e}")

        print("💾 INIT_DB: Committing changes...")
        conn.commit()

        # --- ADDED: (moved up) verify tables & close; removed duplicated block below ---
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [t[0] for t in c.fetchall()]
        print(f"✅ INIT_DB: Tables present: {tables}")
        conn.close()
        print("🔐 INIT_DB: Database connection closed")
        return  # ensure we exit before the old duplicate region

        # --- REMOVED DUPLICATE BLOCK START ---
        # (Previously: second creation of subject_enrollments, assignment_templates,
        #  hardcoded lecturers, second enrollment staging, second commit, verify tables)
        # --- REMOVED DUPLICATE BLOCK END ---

        # ...existing code that followed duplicate (now unreachable after return)...
    except Exception as e:
        print(f"❌ INIT_DB ERROR: {e}")
        import traceback
        traceback.print_exc()
        if 'conn' in locals():
            conn.close()

def init_svn_jobs_table():
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS svn_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folder_id INTEGER NOT NULL,
            student_username TEXT NOT NULL,
            svn_url TEXT NOT NULL,
            revision INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued', -- queued|running|completed|failed
            result_path TEXT,
            log_path TEXT,
            exit_code INTEGER,
            created_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()

def now_iso():
    return datetime.datetime.utcnow().isoformat() + "Z"

def current_semester_year():
    """Return ('SPR'|'AUT', year) based on current UTC month."""
    m = datetime.datetime.utcnow().month
    semester = "SPR" if 1 <= m <= 6 else "AUT"
    year = datetime.datetime.utcnow().year
    return semester, year

def auto_assign_student_to_subject_folders(conn: sqlite3.Connection, student_id: int, subject_id: int) -> int:
    """Assign a student to all existing folders for the given subject."""
    c = conn.cursor()
    # Get subject code
    c.execute("SELECT code FROM subjects WHERE id = ?", (subject_id,))
    row = c.fetchone()
    if not row:
        return 0
    subject_code = row[0]
    # Find folders for subject
    c.execute("SELECT id FROM folders WHERE subject_code = ?", (subject_code,))
    folder_ids = [r[0] for r in c.fetchall()]
    now = now_iso()
    assigned = 0
    for fid in folder_ids:
        c.execute("""
            INSERT OR IGNORE INTO folder_assignments (folder_id, student_id, assigned_at)
            VALUES (?, ?, ?)
        """, (fid, student_id, now))
        assigned += 1
    return assigned

def auto_enroll_student_randomly(conn: sqlite3.Connection, student_id: int, max_subjects: int = 2) -> int:
    """Randomly enroll a student into up to max_subjects existing subjects and assign to current folders."""
    c = conn.cursor()
    # Load all subjects
    c.execute("SELECT id FROM subjects")
    subjects = [r[0] for r in c.fetchall()]
    if not subjects:
        return 0
    # Pick 1..max_subjects randomly (at least 1)
    k = min(max_subjects, len(subjects))
    k = max(1, k)
    pick = random.sample(subjects, k)
    semester, year = current_semester_year()
    count = 0
    for sid in pick:
        # Enroll if not yet enrolled for this sem/year
        c.execute("""
            INSERT OR IGNORE INTO subject_enrollments (student_id, subject_id, enrolled_at, semester, year, status)
            VALUES (?, ?, ?, ?, ?, 'active')
        """, (student_id, sid, now_iso(), semester, year))
        # Also assign this student to all current folders for the subject
        auto_assign_student_to_subject_folders(conn, student_id, sid)
        count += 1
    return count

# --- FastAPI app and routes ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 LIFESPAN: Starting up application...")
    print(f"🗃️ LIFESPAN: Database path: {DB_PATH}")
    init_db()
    print("✅ LIFESPAN: Database initialized")
    # Ensure SSH container is up
    try:
        ensure_ssh_container_running()
    except Exception as e:
        logger.warning(f"SSH container bootstrap error: {e}")
    yield
    # Shutdown (nothing needed for now)
    print("🛑 LIFESPAN: Shutting down application...")

def ensure_ssh_container_running():
    return True


app = FastAPI(title="Automark API", version="0.2.0", lifespan=lifespan)



# Force database initialization if lifespan isn't working
import atexit
init_db()
init_svn_jobs_table()

atexit.register(lambda: None)  # Cleanup on exit

# Mount static folder
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/css", StaticFiles(directory=STATIC_DIR / "css"), name="css")
app.mount("/js", StaticFiles(directory=STATIC_DIR / "js"), name="js")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
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
    subject_code: str
    student_ids: List[int] = []
    files: Optional[List["FileCreate"]] = []  # NEW: lecturer-only files (e.g., marker script)

class FolderUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[str] = None
    max_points: Optional[int] = None
    status: Optional[str] = None
    student_ids: Optional[List[int]] = None
    files: Optional[List["FileCreate"]] = None  # NEW: append-only lecturer files
    remove_file_ids: Optional[List[int]] = None  # NEW: lecturer files to remove

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

class FileCreate(BaseModel):
    name: str
    type: str
    size: int
    content: str  # base64 encoded content
    folder_id: Optional[int] = None
    submission_id: Optional[int] = None

# Resolve forward refs after FileCreate definition
FolderCreate.model_rebuild()
FolderUpdate.model_rebuild()

# New: student submission payload
class StudentSubmissionCreate(BaseModel):
    folder_id: int
    files: List[FileCreate]

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

        if body.role == "student":
            try:
                auto_enroll_student_randomly(conn, user_id)
            except Exception as e:
                logger.warning(f"Auto-enroll failed for {body.username}: {e}")

        conn.commit()

    except sqlite3.IntegrityError as e:
        # --- NEW: student re-registration by SAME EMAIL updates existing record ---
        if body.role == "student" and "email" in str(e).lower():
            try:
                c.execute("SELECT id, username, role FROM users WHERE email = ?", (body.email.strip().lower(),))
                existing = c.fetchone()
                if existing and existing[2] == "student":
                    existing_id, existing_username, _ = existing

                    # If username change requested, ensure it's free
                    new_username = existing_username
                    requested_username = body.username.strip()
                    if requested_username != existing_username:
                        c.execute("SELECT id FROM users WHERE username = ?", (requested_username,))
                        taken = c.fetchone()
                        if not taken:
                            new_username = requested_username  # safe to adopt
                        else:
                            logger.info(f"Username '{requested_username}' taken; retaining '{existing_username}'")

                    c.execute("""
                        UPDATE users
                        SET username = ?, password_hash = ?, first_name = ?, last_name = ?
                        WHERE id = ?
                    """, (
                        new_username,
                        hash_password(body.password),
                        body.first_name.strip(),
                        body.last_name.strip(),
                        existing_id
                    ))
                    conn.commit()
                    user_id = existing_id  # reuse existing id

                    c.execute("SELECT id, username, email, role, first_name, last_name FROM users WHERE id = ?", (user_id,))
                    row = c.fetchone()
                    conn.close()

                    # Attempt SSH user creation for (possibly) new username
                    try:
                        ssh_result = create_ssh_user_for_registration(new_username, body.password)
                        if ssh_result.get("success"):
                            logger.info(f"SSH user ensured/updated for {new_username}")
                        else:
                            logger.warning(f"SSH user creation skipped/failed for {new_username}: {ssh_result.get('error')}")
                    except Exception as se:
                        logger.warning(f"SSH provisioning error (update path) for {new_username}: {se}")

                    return RegisterOut(
                        id=row[0], username=row[1], email=row[2], role=row[3],
                        first_name=row[4], last_name=row[5]
                    )
            except Exception as up_e:
                conn.rollback()
                conn.close()
                logger.error(f"Student update-on-reregister failed: {up_e}")
                raise HTTPException(500, "Could not update existing student record")
        # --- fall back to original behavior ---
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
    except Exception as e:
        logger.error(f"Error creating SSH user for {body.username}: {e}")

    return RegisterOut(
        id=row[0], username=row[1], email=row[2], role=row[3],
        first_name=row[4], last_name=row[5]
    )

@app.post("/api/v1/auth/login", response_model=LoginOut)
def login(body: LoginIn):
    u = body.username.strip()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
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

    # Redirect students to student dashboard
    if role == "student":
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
                "lastName": last_name,
                "redirect": "/studentdash.html"
            }
        )
    # Lecturers go to lecturer dashboard
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
            "lastName": last_name,
            "redirect": "/lecturer-dashboard.html"
        }
    )

# --- Small helpers (added) ---
def _dict_rows(c: sqlite3.Cursor) -> List[dict]:
    return [dict(r) for r in c.fetchall()]

def _ensure_lecturer(current_user: dict):
    if current_user.get("role") != "lecturer":
        raise HTTPException(status_code=403, detail="Only lecturers can perform this action")

def _ensure_folder_owner(c: sqlite3.Cursor, folder_id: int, lecturer_id: int):
    c.execute("SELECT lecturer_id FROM folders WHERE id = ?", (folder_id,))
    row = c.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Folder not found")
    if row[0] != lecturer_id:
        raise HTTPException(status_code=403, detail="You do not own this folder")

def _set_submission_status(submission_id: int, status: str, feedback: Optional[str] = None):
    """Persist submission status and optional feedback."""
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

# NEW: core session validation helper (required by route and Depends)
def _validate_session(token: str):
    """Core session validation logic used by both the route and Depends()"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        now_iso_str = datetime.datetime.utcnow().isoformat() + "Z"
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
        if (d["session_active"] != 1 or d["user_active"] != 1 or now_iso_str > d["expires_at"]):
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
    except sqlite3.Error as e:
        logger.error(f"Database error in session validation: {str(e)}")
        return {"valid": False, "message": f"Database error: {str(e)}"}
    except Exception as e:
        logger.error(f"Unexpected error in session validation: {str(e)}")
        return {"valid": False, "message": f"Server error: {str(e)}"}
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
def list_folders(current_user: dict = Depends(get_current_user)):
    """List assignments (folders) owned by the current lecturer."""
    _ensure_lecturer(current_user)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        c.execute("""
            SELECT id, name, description, due_date, max_points, status,
                   created_at, updated_at, lecturer_id, subject_code, lecturer_file_ids
            FROM folders
            WHERE lecturer_id = ?
            ORDER BY COALESCE(updated_at, created_at) DESC
        """, (current_user["id"],))
        rows = _dict_rows(c)
        # Add derived count for convenience
        for r in rows:
            try:
                r["lecturer_files_count"] = len(json.loads(r.get("lecturer_file_ids") or "[]"))
            except Exception:
                r["lecturer_files_count"] = 0
        return rows
    finally:
        conn.close()

@app.get("/api/v1/student/folders")
def get_student_folders(current_user: dict = Depends(get_current_user)):
    """List folders (assignments) visible to the current student by subject enrollments (no lecturer files exposed)."""
    if current_user["role"] != "student":
        raise HTTPException(status_code=403, detail="Only students can access their assignments")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        c.execute("""
            SELECT f.id, f.name, f.description, f.due_date, f.max_points, f.status,
                   f.created_at, f.updated_at, f.lecturer_id, f.subject_code
            FROM folders f
            JOIN subjects s ON s.code = f.subject_code
            JOIN subject_enrollments se 
                ON se.subject_id = s.id 
               AND se.student_id = ? 
               AND se.status = 'active'
            WHERE LOWER(f.status) IN ('published','active')
            ORDER BY COALESCE(f.due_date, f.created_at) ASC
        """, (current_user["id"],))
        # lecturer_file_ids deliberately excluded from SELECT
        return _dict_rows(c)
    finally:
        conn.close()

@app.post("/api/v1/folders")
async def create_folder(folder: FolderCreate, current_user: dict = Depends(get_current_user)):
    """Create a new assignment folder (optionally with lecturer marker/reference files)."""
    if current_user["role"] != "lecturer":
        raise HTTPException(status_code=403, detail="Only lecturers can create folders")

    _ensure_lecturer_files_column()  # NEW: make sure column exists before insert
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        now = now_iso()
        c.execute("""
            INSERT INTO folders (name, description, due_date, max_points, status,
                                 created_at, updated_at, lecturer_id, subject_code, lecturer_file_ids)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            folder.name.strip(),
            (folder.description or None),
            (folder.due_date or None),
            int(folder.max_points or 100),
            (folder.status or "draft"),
            now,
            now,
            current_user["id"],
            folder.subject_code.strip(),
            None  # placeholder; update after file insert
        ))
        folder_id = c.lastrowid

        lecturer_file_ids_json = None
        # Store lecturer files if provided
        if folder.files:
            file_ids = _insert_lecturer_files(c, current_user["id"], folder.files)
            lecturer_file_ids_json = json.dumps(file_ids)
            c.execute("UPDATE folders SET lecturer_file_ids = ? WHERE id = ?", (lecturer_file_ids_json, folder_id))

        # Auto-assign actively enrolled students (unchanged)
        assigned = 0
        try:
            c.execute("SELECT id FROM subjects WHERE code = ?", (folder.subject_code.strip(),))
            subj = c.fetchone()
            if subj:
                subject_id = subj["id"] if isinstance(subj, sqlite3.Row) else subj[0]
                c.execute("""
                    SELECT student_id 
                    FROM subject_enrollments 
                    WHERE subject_id = ? AND status = 'active'
                """, (subject_id,))
                student_ids = [r[0] for r in c.fetchall()]
                for sid in student_ids:
                    c.execute("""
                        INSERT OR IGNORE INTO folder_assignments (folder_id, student_id, assigned_at)
                        VALUES (?, ?, ?)
                    """, (folder_id, sid, now))
                assigned = len(student_ids)
        except Exception as e:
            logger.warning(f"Auto-assign students failed for folder {folder_id}: {e}")

        conn.commit()

        lecturer_files_count = 0
        if lecturer_file_ids_json:
            try:
                lecturer_files_count = len(json.loads(lecturer_file_ids_json))
            except Exception:
                pass

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
            "subject_code": folder.subject_code,
            "assigned_students_count": assigned,
            "lecturer_files_count": lecturer_files_count
        }

    except sqlite3.Error as e:
        conn.rollback()
        raise HTTPException(500, f"Database error: {str(e)}")
    finally:
        conn.close()

@app.get("/api/v1/folders/{folder_id}/lecturer-files")
def get_lecturer_files(folder_id: int, current_user: dict = Depends(get_current_user)):
    """Return metadata for lecturer files attached to a folder (owner only)."""
    _ensure_lecturer(current_user)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        _ensure_folder_owner(c, folder_id, current_user["id"])
        c.execute("SELECT lecturer_file_ids FROM folders WHERE id = ?", (folder_id,))
        row = c.fetchone()
        if not row:
            raise HTTPException(404, "Folder not found")
        file_ids = []
        try:
            file_ids = json.loads(row[0] or "[]")
        except Exception:
            file_ids = []
        if not file_ids:
            return []
        placeholders = ",".join(["?"] * len(file_ids))
        c.execute(f"""
            SELECT id, name, type, size, uploaded_at, uploaded_by
            FROM files
            WHERE id IN ({placeholders})
            ORDER BY id
        """, file_ids)
        return _dict_rows(c)
    finally:
        conn.close()

@app.put("/api/v1/folders/{folder_id}")
def update_folder(folder_id: int, payload: FolderUpdate, current_user: dict = Depends(get_current_user)):
    """Update an assignment (folder) and optionally append lecturer files or reassign students."""
    _ensure_lecturer(current_user)
    _ensure_lecturer_files_column()  # NEW: ensure column before update
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        _ensure_folder_owner(c, folder_id, current_user["id"])

        # Fetch current lecturer files list
        c.execute("SELECT lecturer_file_ids FROM folders WHERE id = ?", (folder_id,))
        row = c.fetchone()
        existing_file_ids = []
        if row and row[0]:
            try:
                existing_file_ids = json.loads(row[0])
            except Exception:
                existing_file_ids = []

        # NEW: remove specified lecturer files
        if payload.remove_file_ids:
            remove_set = set(int(x) for x in payload.remove_file_ids)
            to_delete = [fid for fid in existing_file_ids if fid in remove_set]
            if to_delete:
                existing_file_ids = [fid for fid in existing_file_ids if fid not in remove_set]
                placeholders = ",".join(["?"] * len(to_delete))
                c.execute(f"DELETE FROM files WHERE id IN ({placeholders})", to_delete)

        # Append new lecturer files if provided
        if payload.files:
            new_ids = _insert_lecturer_files(c, current_user["id"], payload.files)
            existing_file_ids.extend(new_ids)

        # Persist updated lecturer_file_ids if changed
        c.execute("UPDATE folders SET lecturer_file_ids = ? WHERE id = ?",
                  (json.dumps(existing_file_ids), folder_id))

        fields = []
        values = []
        if payload.name is not None:
            fields.append("name = ?"); values.append(payload.name.strip())
        if payload.description is not None:
            fields.append("description = ?"); values.append(payload.description.strip() if payload.description else None)
        if payload.due_date is not None:
            fields.append("due_date = ?"); values.append(payload.due_date or None)
        if payload.max_points is not None:
            fields.append("max_points = ?"); values.append(int(payload.max_points))
        if payload.status is not None:
            fields.append("status = ?"); values.append(payload.status.strip())
        fields.append("updated_at = ?"); values.append(now_iso())

        if fields:
            q = "UPDATE folders SET " + ", ".join(fields) + " WHERE id = ?"
            values.append(folder_id)
            c.execute(q, values)

        if payload.student_ids is not None:
            new_ids = set(int(x) for x in payload.student_ids)
            c.execute("SELECT student_id FROM folder_assignments WHERE folder_id = ?", (folder_id,))
            current_ids = set(r[0] for r in c.fetchall())
            to_add = new_ids - current_ids
            to_del = current_ids - new_ids
            if to_del:
                placeholders = ",".join(["?"] * len(to_del))
                c.execute(f"DELETE FROM folder_assignments WHERE folder_id = ? AND student_id IN ({placeholders})",
                          (folder_id, *to_del))
            for sid in to_add:
                c.execute("""
                    INSERT OR IGNORE INTO folder_assignments (folder_id, student_id, assigned_at)
                    VALUES (?, ?, ?)
                """, (folder_id, sid, now_iso()))

        conn.commit()

        c.execute("""
            SELECT id, name, description, due_date, max_points, status,
                   created_at, updated_at, lecturer_id, subject_code, lecturer_file_ids
            FROM folders WHERE id = ?
        """, (folder_id,))
        out = dict(c.fetchone())
        # Add derived field
        try:
            out["lecturer_files_count"] = len(json.loads(out.get("lecturer_file_ids") or "[]"))
        except Exception:
            out["lecturer_files_count"] = 0
        return out
    except HTTPException:
        conn.rollback()
        raise
    except sqlite3.Error as e:
        conn.rollback()
        raise HTTPException(500, f"Database error: {str(e)}")
    finally:
        conn.close()

@app.delete("/api/v1/folders/{folder_id}")
def delete_folder(folder_id: int, current_user: dict = Depends(get_current_user)):
    """Delete an assignment (folder), its submissions and related file blobs."""
    _ensure_lecturer(current_user)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        _ensure_folder_owner(c, folder_id, current_user["id"])

        # Collect submission file ids to delete file blobs
        c.execute("SELECT id, file_ids FROM submissions WHERE folder_id = ?", (folder_id,))
        subs = _dict_rows(c)
        file_ids = []
        for s in subs:
            try:
                file_ids.extend(json.loads(s.get("file_ids") or "[]"))
            except Exception:
                pass

        # Delete submissions
        c.execute("DELETE FROM submissions WHERE folder_id = ?", (folder_id,))
        # Delete assigned students
        c.execute("DELETE FROM folder_assignments WHERE folder_id = ?", (folder_id,))
        # Delete files referenced by those submissions
        if file_ids:
            placeholders = ",".join(["?"] * len(file_ids))
            c.execute(f"DELETE FROM files WHERE id IN ({placeholders})", file_ids)
        # Finally delete the folder
        c.execute("DELETE FROM folders WHERE id = ?", (folder_id,))

        conn.commit()
        return {"deleted": True}
    except HTTPException:
        conn.rollback()
        raise
    except sqlite3.Error as e:
        conn.rollback()
        raise HTTPException(500, f"Database error: {str(e)}")
    finally:
        conn.close()

@app.get("/api/v1/folders/{folder_id}/assignments")
def list_folder_assignments(folder_id: int, current_user: dict = Depends(get_current_user)):
    """Return assigned students for a given folder (lecturer must own)."""
    _ensure_lecturer(current_user)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        _ensure_folder_owner(c, folder_id, current_user["id"])
        # Return only assigned students with is_assigned flag (UI only needs IDs)
        c.execute("""
            SELECT u.id, 1 AS is_assigned
            FROM users u
            JOIN folder_assignments fa ON fa.student_id = u.id
            WHERE fa.folder_id = ? AND u.role = 'student' AND u.is_active = 1
        """, (folder_id,))
        return _dict_rows(c)
    finally:
        conn.close()

@app.get("/api/v1/submissions")
def list_submissions(current_user: dict = Depends(get_current_user)):
    """List submissions for folders owned by the current lecturer (includes student names)."""
    _ensure_lecturer(current_user)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        c.execute("""
            SELECT s.id, s.folder_id, s.student_id, s.submitted_at, s.score, s.feedback,
                   s.status, s.graded_at, s.revisions, s.file_ids,
                   u.first_name, u.last_name, u.username, f.name AS folder_name
            FROM submissions s
            JOIN users u ON u.id = s.student_id
            JOIN folders f ON f.id = s.folder_id
            WHERE f.lecturer_id = ?
            ORDER BY s.submitted_at DESC
        """, (current_user["id"],))
        rows = _dict_rows(c)
        # Normalize file_ids into list
        for r in rows:
            try:
                r["file_ids"] = json.loads(r.get("file_ids") or "[]")
            except Exception:
                r["file_ids"] = []
        return rows
    finally:
        conn.close()

# ------------------------------
# Student-specific endpoints
# ------------------------------
@app.get("/api/v1/student/subjects")
def get_student_subjects(current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "student":
        raise HTTPException(status_code=403, detail="Only students can access their subjects")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        c.execute("""
            SELECT DISTINCT s.id, s.code, s.name, s.lecturer_id, s.created_at
            FROM subjects s
            JOIN subject_enrollments se 
                ON se.subject_id = s.id 
               AND se.student_id = ?
               AND se.status = 'active'
            JOIN folders f ON f.subject_code = s.code
            WHERE LOWER(f.status) IN ('published','active')
            ORDER BY s.code
        """, (current_user["id"],))
        rows = c.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

# List students (lecturers only) for enrollment UI
@app.get("/api/v1/students")
def list_students(current_user: dict = Depends(get_current_user)):
    _ensure_lecturer(current_user)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        c.execute("""
            SELECT id, username, email, first_name, last_name
            FROM users
            WHERE role = 'student' AND is_active = 1
            ORDER BY first_name, last_name
        """)
        return _dict_rows(c)
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
    
    template_files = {}
    
    # Create a single assignment instruction file
    template_files["ASSIGNMENT_INSTRUCTIONS.md"] = f"""# {assignment_name}

## Assignment Overview
This assignment focuses on [assignment objectives]. Please read these instructions carefully and complete all required tasks.

## Student Information
- **Student Name**: [Your Full Name]
- **Student ID**: [Your Student ID]
- **Subject**: [Subject Code]
- **Due Date**: [Check course website for official due date]

## Assignment Description
[Detailed assignment description will be provided by your lecturer]

## Requirements
1. Complete all required tasks as outlined by your lecturer
2. Follow coding standards and best practices
3. Include proper documentation and comments
4. Test your work thoroughly before submission

## Submission Instructions
1. Complete your work in this directory
2. Add any files you create using: `svn add filename`
3. Commit your work using SVN:
   ```bash
   svn add .
   svn commit -m "Assignment submission - [Your Name]"
   ```
4. You can submit multiple times - your latest commit before the deadline will be graded

## Getting Help
- Check course materials and lecture notes
- Ask questions during tutorial sessions
- Contact your lecturer if you need clarification

## Academic Integrity
- This work must be your own
- Follow university academic integrity policies
- Cite any sources or references used

---
**Good luck with your assignment!**
"""
    
    return template_files

@app.post("/api/v1/folders/{folder_id}/marker")
def upload_marker_for_folder(
    folder_id: int,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    # Only lecturers can upload markers for folders they own
    if current_user["role"] != "lecturer":
        raise HTTPException(403, "Only lecturers can upload marker")

    # ensure lecturer owns the folder
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    try:
        c.execute("SELECT lecturer_id FROM folders WHERE id = ?", (folder_id,))
        row = c.fetchone()
        if not row:
            raise HTTPException(404, "Folder not found")
        if row[0] != current_user["id"]:
            raise HTTPException(403, "You do not own this folder")
    finally:
        conn.close()

    marker_dir = storage.ASSIGN_BASE / str(folder_id) / "marker"
    marker_dir.mkdir(parents=True, exist_ok=True)

    # Save the uploaded file
    dest = marker_dir / file.filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    # If a zip is uploaded, extract it
    if dest.suffix.lower() == ".zip":
        with zipfile.ZipFile(dest) as z:
            z.extractall(marker_dir)

        # Try to find run.sh (supports a top-level folder inside the zip)
        run_sh_flat = marker_dir / "run.sh"
        found_path = None

        if run_sh_flat.exists():
            found_path = run_sh_flat
        else:
            # look one or two levels deep for run.sh
            for root, dirs, files in os.walk(marker_dir):
                # skip the marker_dir itself (we already checked)
                if Path(root) == marker_dir:
                    continue
                if "run.sh" in files:
                    candidate = Path(root) / "run.sh"
                    found_path = candidate
                    break

        # If we found a nested run.sh, move it up to marker/
        if found_path and found_path != run_sh_flat:
            shutil.move(str(found_path), str(run_sh_flat))
            # optionally clean up the now-empty top-level subdir created by the zip
            try:
                # remove empty dirs under marker_dir (best-effort)
                for p in sorted(marker_dir.glob("*/"), key=lambda p: len(str(p)), reverse=True):
                    try:
                        p.rmdir()
                    except OSError:
                        pass
            except Exception:
                pass

        # Ensure run.sh is executable
        if run_sh_flat.exists():
            os.chmod(run_sh_flat, 0o755)

        # Remove the uploaded zip to keep the folder clean (optional)
        try:
            dest.unlink(missing_ok=True)
        except Exception:
            pass

    else:
        # Non-zip uploads: if it's named run.sh, ensure executable
        if dest.name == "run.sh":
            os.chmod(dest, 0o755)

    return {"ok": True, "folder_id": folder_id, "marker_path": str(marker_dir)}



class SVNJobIn(BaseModel):
    folder_id: int
    student_username: str
    svn_url: str
    revision: int

def _run_svn_job(job_id: int):
    """Export code from SVN and run marker in a fresh Docker container."""
    # update -> running
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    try:
        c.execute("UPDATE svn_jobs SET status='running', started_at=? WHERE id=?",
                  (now_iso(), job_id))
        conn.commit()
        # fetch job row
        c.execute("SELECT folder_id, svn_url, revision FROM svn_jobs WHERE id=?", (job_id,))
        row = c.fetchone()
        if not row:
            return
        folder_id, svn_url, revision = row
    finally:
        conn.close()

    # Paths
    code_dir    = storage.SUBMISSIONS_BASE / str(job_id) / "src"
    results_dir = storage.RESULTS_BASE / str(job_id)
    marker_dir  = storage.ASSIGN_BASE / str(folder_id) / "marker"
    code_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    # 1) Export student code
    exit_code = 1
    logs_text = ""
    try:
        worker.svn_export(svn_url, revision, str(code_dir))
        exit_code, logs_text = docker_runner.run_job(job_id, code_dir, marker_dir, results_dir)
    except Exception as e:
        logs_text = f"ERROR: {e}\n" + traceback.format_exc()

    # Write logs
    log_path = results_dir / "runner.log"
    try:
        log_path.write_text(logs_text, encoding="utf-8")
    except Exception:
        pass

    # update -> completed/failed
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    try:
        c.execute("""UPDATE svn_jobs
                     SET status=?, exit_code=?, result_path=?, log_path=?, finished_at=?
                     WHERE id=?""",
                  ("completed" if exit_code == 0 else "failed",
                   int(exit_code),
                   str(results_dir),
                   str(log_path),
                   now_iso(),
                   job_id))
        conn.commit()
    finally:
        conn.close()

@app.post("/api/v1/submissions/receive_svn")
def receive_submission_svn(body: SVNJobIn):
    """Called by SVN post-commit (or poller) to trigger a sandbox run."""
    now = now_iso()
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    try:
        # basic validation: folder exists
        c.execute("SELECT id FROM folders WHERE id = ?", (body.folder_id,))
        if not c.fetchone():
            raise HTTPException(404, "Folder not found")

        c.execute("""INSERT INTO svn_jobs(folder_id, student_username, svn_url, revision, status, created_at)
                     VALUES(?,?,?,?, 'queued', ?)""",
                  (body.folder_id, body.student_username, body.svn_url, int(body.revision), now))
        job_id = c.lastrowid
        conn.commit()
    finally:
        conn.close()

    # kick off a background thread for this job
    threading.Thread(target=_run_svn_job, args=(job_id,), daemon=True).start()
    return {"job_id": job_id, "status": "queued"}

@app.get("/api/v1/svn_jobs/{job_id}")
def get_svn_job(job_id: int):
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        c.execute("""SELECT id, folder_id, student_username, svn_url, revision, status,
                            exit_code, result_path, log_path, created_at, started_at, finished_at
                     FROM svn_jobs WHERE id=?""", (job_id,))
        row = c.fetchone()
        if not row:
            raise HTTPException(404, "Job not found")
        return dict(row)
    finally:
        conn.close()


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
        if not subject_result or subject_result[0] != current_user["id"]:
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
    """Get subjects. Lecturers: subjects they teach. Students: subjects from active enrollments."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        if current_user["role"] == "lecturer":
            c.execute("""
                SELECT id, code, name, lecturer_id, created_at
                FROM subjects
                WHERE lecturer_id = ?
                ORDER BY code
            """, (current_user["id"],))
            return _dict_rows(c)
        else:
            c.execute("""
                SELECT DISTINCT s.id, s.code, s.name, s.lecturer_id, s.created_at
                FROM subjects s
                JOIN subject_enrollments se 
                    ON se.subject_id = s.id 
                   AND se.student_id = ?
                   AND se.status = 'active'
                ORDER BY s.code
            """, (current_user["id"],))
            return _dict_rows(c)
    finally:
        conn.close()

# New: list my submissions (with file names, no content)
@app.get("/api/v1/student/submissions")
def get_my_submissions(folder_id: Optional[int] = None, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "student":
        raise HTTPException(status_code=403, detail="Only students can access their submissions")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        params = [current_user["id"]]
        sql = """
            SELECT id, folder_id, student_id, submitted_at, score, feedback, status, graded_at, revisions, file_ids
            FROM submissions
            WHERE student_id = ?
        """
        if folder_id is not None:
            sql += " AND folder_id = ?"
            params.append(folder_id)
        sql += " ORDER BY submitted_at DESC"
        c.execute(sql, params)
        rows = [dict(r) for r in c.fetchall()]
        # Hydrate files (names only)
        for r in rows:
            file_ids = []
            try:
                file_ids = json.loads(r.get("file_ids") or "[]")
            except Exception:
                file_ids = []
            r["file_ids"] = file_ids
            r["files"] = []
            if file_ids:
                placeholders = ",".join(["?"] * len(file_ids))
                c.execute(f"SELECT id, name FROM files WHERE id IN ({placeholders})", file_ids)
                r["files"] = [dict(x) for x in c.fetchall()]
        return rows
    finally:
        conn.close()

# New: create/append a submission with uploaded files
@app.post("/api/v1/student/submissions")
def create_or_update_submission(payload: StudentSubmissionCreate, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "student":
        raise HTTPException(status_code=403, detail="Only students can submit")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        # Verify folder belongs to a subject the student is actively enrolled in and is open
        c.execute("""
          SELECT f.id, f.status
          FROM folders f
          JOIN subjects s ON s.code = f.subject_code
          JOIN subject_enrollments se 
            ON se.subject_id = s.id 
           AND se.student_id = ?
           AND se.status = 'active'
          WHERE f.id = ?
        """, (current_user["id"], payload.folder_id))
        frow = c.fetchone()
        if not frow:
            raise HTTPException(403, "You are not enrolled in the subject for this assignment")
        status = (frow["status"] or "").lower()
        if status not in ("published", "active"):
            raise HTTPException(400, "Assignment is not open for submissions")

        now = now_iso()
        # Insert files
        new_file_ids = []
        for fl in payload.files:
            try:
                content_b64 = fl.content
                # Accept data URLs
                if "," in content_b64:
                    content_b64 = content_b64.split(",", 1)[1]
                blob = base64.b64decode(content_b64)
            except Exception:
                raise HTTPException(400, "Invalid file content encoding")
            c.execute("""
              INSERT INTO files (name, type, size, content, uploaded_at, uploaded_by)
              VALUES (?, ?, ?, ?, ?, ?)
            """, (fl.name, fl.type or "application/octet-stream", fl.size or len(blob), sqlite3.Binary(blob), now, current_user["id"]))
            new_file_ids.append(c.lastrowid)

        # Find existing submission
        c.execute("""
          SELECT id, file_ids, revisions FROM submissions
          WHERE folder_id = ? AND student_id = ?
          ORDER BY id DESC LIMIT 1
        """, (payload.folder_id, current_user["id"]))
        srow = c.fetchone()

        if srow:
            existing_ids = []
            try:
                existing_ids = json.loads(srow["file_ids"] or "[]")
            except Exception:
                existing_ids = []
            merged = existing_ids + new_file_ids
            c.execute("""
              UPDATE submissions
              SET submitted_at = ?, status = 'submitted', file_ids = ?, revisions = ?
              WHERE id = ?
            """, (now, json.dumps(merged), int(srow["revisions"] or 1) + 1, srow["id"]))
            submission_id = srow["id"]
            file_ids_out = merged
        else:
            c.execute("""
              INSERT INTO submissions (folder_id, student_id, submitted_at, status, revisions, file_ids)
              VALUES (?, ?, ?, 'submitted', 1, ?)
            """, (payload.folder_id, current_user["id"], now, json.dumps(new_file_ids)))
            submission_id = c.lastrowid
            file_ids_out = new_file_ids

        # Return submission with file names
        files_meta = []
        if file_ids_out:
            placeholders = ",".join(["?"] * len(file_ids_out))
            c.execute(f"SELECT id, name FROM files WHERE id IN ({placeholders})", file_ids_out)
            files_meta = [dict(x) for x in c.fetchall()]
        conn.commit()
        return {
            "id": submission_id,
            "folder_id": payload.folder_id,
            "student_id": current_user["id"],
            "submitted_at": now,
            "status": "submitted",
            "revisions": len(file_ids_out),  # simple indicator
            "file_ids": file_ids_out,
            "files": files_meta
        }
    except HTTPException:
        conn.rollback()
        raise
    except sqlite3.Error as e:
        conn.rollback()
        raise HTTPException(500, f"Database error: {str(e)}")
    finally:
        conn.close()

# New: download a file (returns JSON with base64 content)
@app.get("/api/v1/files/{file_id}")
def get_file(file_id: int, current_user: dict = Depends(get_current_user)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        c.execute("SELECT id, name, type, size, content, uploaded_by FROM files WHERE id = ?", (file_id,))
        r = c.fetchone()
        if not r:
            raise HTTPException(404, "File not found")
        r = dict(r)
        # Security: allow owner or lecturers
        if current_user["role"] != "lecturer" and current_user["id"] != r["uploaded_by"]:
            raise HTTPException(403, "Forbidden")
        content_b64 = base64.b64encode(r["content"]).decode("utf-8")
        return {"id": r["id"], "name": r["name"], "type": r["type"], "size": r["size"], "content": content_b64}
    except HTTPException:
        raise
    except sqlite3.Error as e:
        raise HTTPException(500, f"Database error: {str(e)}")
    finally:
        conn.close()

def _ensure_lecturer_files_column():
    """Ensure folders table has lecturer_file_ids column (runtime safety for older DBs)."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("PRAGMA table_info(folders);")
        cols = {r[1] for r in c.fetchall()}
        if "lecturer_file_ids" not in cols:
            try:
                c.execute("ALTER TABLE folders ADD COLUMN lecturer_file_ids TEXT")
                conn.commit()
                logger.info("Added missing lecturer_file_ids column to folders table at runtime.")
            except sqlite3.OperationalError as e:
                logger.warning(f"Could not add lecturer_file_ids column (maybe race condition): {e}")
    except Exception as e:
        logger.error(f"_ensure_lecturer_files_column failed: {e}")
    finally:
        try:
            conn.close()
        except:
            pass

# --- NEW: lecturer file insertion helper (used by create/update folder) ---
def _insert_lecturer_files(c: sqlite3.Cursor, uploader_id: int, files: List[FileCreate]) -> List[int]:
    """
    Persist lecturer-only files (e.g., marker scripts) into files table.
    Returns list of inserted file IDs.
    """
    inserted: List[int] = []
    if not files:
        return inserted
    now = now_iso()
    for f in files:
        try:
            content_b64 = f.content
            # Accept data URLs
            if "," in content_b64:
                content_b64 = content_b64.split(",", 1)[1]
            blob = base64.b64decode(content_b64)
        except Exception as e:
            logger.warning(f"Skipping file '{getattr(f,'name', '?')}' (decode error): {e}")
            continue
        size = f.size or len(blob)
        if size != len(blob):
            # Trust actual decoded length
            size = len(blob)
        c.execute("""
            INSERT INTO files (name, type, size, content, uploaded_at, uploaded_by)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            f.name,
            f.type or "application/octet-stream",
            size,
            sqlite3.Binary(blob),
            now,
            uploader_id
        ))
        inserted.append(c.lastrowid)
    return inserted