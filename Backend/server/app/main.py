# Backend/server/app/main.py
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
import hashlib, sqlite3, uuid, datetime
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import logging
import os
from typing import List, Optional, Dict
import json
from contextlib import asynccontextmanager
import base64

# SSH user management
from ssh_user_manager import create_ssh_user_for_registration

# Database path
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "automark.db"))
STATIC_DIR = BASE_DIR / "static"

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Single source for default student → subjects mapping
DEFAULT_ASSIGNED_SUBJECTS: Dict[str, List[str]] = {
    "student_alice": ["INFS 8586", "COMP 0067"],
    "student_bob": ["COMP 0420", "COMP 5055"],
    "student_carol": ["COMP 0067", "INFS 8586", "COMP 0420"],
}

def get_assigned_subject_codes_for_username(username: str) -> List[str]:
    codes = DEFAULT_ASSIGNED_SUBJECTS.get(username)
    if codes:
        return codes
    # Fallback: no subjects unless explicitly mapped
    return []

def init_db():
    try:
        print(f"🗃️ INIT_DB: Connecting to {DB_PATH}")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

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
        # Hardcoded student information with shuffled subject assignments
        students = [
            {
                "username": "student_alice",
                "email": "alice.smith@student.automark.com",
                "password": "alicepass123",
                "first_name": "Alice",
                "last_name": "Smith",
                "assigned_subjects": ["INFS 8586", "COMP 0067"]
            },
            {
                "username": "student_bob",
                "email": "bob.johnson@student.automark.com",
                "password": "bobpass123",
                "first_name": "Bob",
                "last_name": "Johnson",
                "assigned_subjects": ["COMP 0420", "COMP 5055"]
            },
            {
                "username": "student_carol",
                "email": "carol.williams@student.automark.com",
                "password": "carolpass123",
                "first_name": "Carol",
                "last_name": "Williams",
                "assigned_subjects": ["COMP 0067", "INFS 8586", "COMP 0420"]
            }
        ]

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
                    print(f"   📚 Assigned to subjects: {', '.join(student['assigned_subjects'])}")
                    
                    # Create SSH user for student
                    try:
                        ssh_result = create_ssh_user_for_registration(student["username"], student["password"])
                        if ssh_result["success"]:
                            print(f"✅ Created SSH user for {student['username']}")
                        else:
                            print(f"⚠️  SSH user creation failed for {student['username']}: {ssh_result.get('error')}")
                    except Exception as e:
                        print(f"⚠️  SSH user creation error for {student['username']}: {e}")
                    
                    # Auto-assign student to assignments for their specific subjects only
                    if student["assigned_subjects"]:
                        placeholders = ",".join(["?"] * len(student["assigned_subjects"]))
                        c.execute(f"SELECT id FROM folders WHERE subject_code IN ({placeholders})", student["assigned_subjects"])
                        assigned_folder_ids = [row[0] for row in c.fetchall()]
                        for folder_id in assigned_folder_ids:
                            c.execute("""
                                INSERT OR IGNORE INTO folder_assignments (folder_id, student_id, assigned_at)
                                VALUES (?, ?, ?)
                            """, (folder_id, student_id, now))
                        if assigned_folder_ids:
                            print(f"   ✅ Auto-assigned to {len(assigned_folder_ids)} assignments in their subjects")
                
                else:
                    print(f"⚠️  Student already exists: {student['username']}")
            except sqlite3.Error as e:
                print(f"❌ Failed to create student {student['username']}: {e}")
                continue

        print("💾 INIT_DB: Committing changes...")

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
                    {"code": "COMP 0067", "name": "Database and Design"}
                ]
            },
            {
                "username": "lecturer_prog",
                "email": "prog.lecturer@automark.com", 
                "password": "progpassword123",
                "first_name": "Sarah",
                "last_name": "Johnson",
                "subjects": [
                    {"code": "COMP 0420", "name": "Programming Techniques"}
                ]
            },
            {
                "username": "lecturer_oop",
                "email": "oop.lecturer@automark.com",
                "password": "ooppassword123", 
                "first_name": "Robert",
                "last_name": "Williams",
                "subjects": [
                    {"code": "INFS 8586", "name": "Object Oriented Programming"},
                    {"code": "COMP 5055", "name": "Software Engineering"}
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
        
        # Verify tables were created
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [t[0] for t in c.fetchall()]
        print(f"✅ INIT_DB: Created tables: {tables}")
        
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
    subject_code: str  # Added required field
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

# New: student submission payload
class StudentSubmissionCreate(BaseModel):
    folder_id: int
    files: List[FileCreate]

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
    print(f"Database exists: {DB_PATH.exists()}")
    
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
        
        # Assign student to subjects/assignments based on mapping only
        if body.role == "student":
            subject_codes = get_assigned_subject_codes_for_username(body.username.strip())
            if subject_codes:
                placeholders = ",".join(["?"] * len(subject_codes))
                c.execute(f"SELECT id FROM folders WHERE subject_code IN ({placeholders})", subject_codes)
                folder_ids = [row[0] for row in c.fetchall()]
                assign_time = now_iso()
                for folder_id in folder_ids:
                    c.execute("""
                        INSERT OR IGNORE INTO folder_assignments (folder_id, student_id, assigned_at)
                        VALUES (?, ?, ?)
                    """, (folder_id, user_id, assign_time))
                conn.commit()
                print(f"✅ Auto-assigned student {body.username} to {len(folder_ids)} assignments in subjects {subject_codes}")
            else:
                print(f"ℹ️ No default subject mapping for {body.username}; no assignments created")
            
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

# Add this fix to the session validation endpoint around line 238
@app.get("/api/v1/auth/session/{token}")
def validate_session(token: str):
    """Validate session token and return user info"""
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
        
        session_data = dict(row)
        if (session_data["session_active"] != 1 or 
            session_data["user_active"] != 1 or 
            now > session_data["expires_at"]):
            return {"valid": False, "message": "Session expired or inactive"}
        
        return {
            "valid": True,
            "user": {
                "id": session_data["id"],
                "username": session_data["username"],
                "email": session_data["email"],
                "role": session_data["role"],
                "firstName": session_data["first_name"],
                "lastName": session_data["last_name"]
            }
        }
    except sqlite3.Error as e:
        logger.error(f"Database error in session validation: {str(e)}")
        return {"valid": False, "message": f"Database error: {str(e)}"}
    except Exception as e:
        logger.error(f"Unexpected error in session validation: {str(e)}")
        return {"valid": False, "message": f"Server error: {str(e)}"}
    finally:
        conn.close()
        
from fastapi import Header

async def get_current_user(request: Request):
    """Get current user from session token"""
    # Try to get token from Authorization header
    auth_header = request.headers.get("Authorization")
    token = None
    
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
    else:
        # Try to get token from query parameter (for debugging)
        token = request.query_params.get("token")
    
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Validate session token
    result = validate_session(token)
    if not result["valid"]:
        raise HTTPException(status_code=401, detail=result["message"])
    
    return result["user"]

# ------------------------------
# Helper utilities for lecturers
# ------------------------------
def _dict_rows(cursor):
    return [dict(r) for r in cursor.fetchall()]

def _ensure_lecturer(user: dict):
    if user.get("role") != "lecturer":
        raise HTTPException(status_code=403, detail="Only lecturers can access this resource")

def _ensure_folder_owner(c: sqlite3.Cursor, folder_id: int, lecturer_id: int):
    c.execute("SELECT lecturer_id FROM folders WHERE id = ?", (folder_id,))
    row = c.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Folder not found")
    if row[0] != lecturer_id:
        raise HTTPException(status_code=403, detail="You do not own this folder")

# ------------------------------
# Lecturer + shared endpoints
# ------------------------------

@app.get("/api/v1/subjects")
def list_subjects(current_user: dict = Depends(get_current_user)):
    """List all subjects (lecturers will filter client-side or use lecturer_id)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        c.execute("""
            SELECT id, code, name, lecturer_id, created_at
            FROM subjects
            ORDER BY code
        """)
        return _dict_rows(c)
    finally:
        conn.close()

@app.get("/api/v1/students")
def list_students(current_user: dict = Depends(get_current_user)):
    """List all active students (lecturer-only)."""
    _ensure_lecturer(current_user)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        c.execute("""
            SELECT id, username, email, first_name, last_name, created_at
            FROM users
            WHERE role = 'student' AND is_active = 1
            ORDER BY created_at DESC
        """)
        return _dict_rows(c)
    finally:
        conn.close()

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
                   created_at, updated_at, lecturer_id, subject_code
            FROM folders
            WHERE lecturer_id = ?
            ORDER BY COALESCE(updated_at, created_at) DESC
        """, (current_user["id"],))
        return _dict_rows(c)
    finally:
        conn.close()

@app.post("/api/v1/folders")
def create_folder(payload: FolderCreate, current_user: dict = Depends(get_current_user)):
    """Create an assignment (folder) and optionally assign students."""
    _ensure_lecturer(current_user)
    now = now_iso()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO folders (name, description, due_date, max_points, status,
                                 created_at, updated_at, lecturer_id, subject_code)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            payload.name.strip(),
            (payload.description or None),
            (payload.due_date or None),
            int(payload.max_points or 100),
            (payload.status or "draft"),
            now,
            now,
            current_user["id"],
            payload.subject_code.strip()
        ))
        folder_id = c.lastrowid

        # Optional: assign students (explicit)
        if payload.student_ids:
            assign_time = now
            for sid in payload.student_ids:
                c.execute("""
                    INSERT OR IGNORE INTO folder_assignments (folder_id, student_id, assigned_at)
                    VALUES (?, ?, ?)
                """, (folder_id, int(sid), assign_time))
        else:
            # Default auto-assign: all students whose assigned_subjects include this subject_code
            subject_code = payload.subject_code.strip()
            assign_time = now
            c.execute("SELECT id, username FROM users WHERE role='student' AND is_active=1")
            rows = c.fetchall()
            auto_count = 0
            for sid, uname in rows:
                if subject_code in get_assigned_subject_codes_for_username(uname):
                    c.execute("""
                        INSERT OR IGNORE INTO folder_assignments (folder_id, student_id, assigned_at)
                        VALUES (?, ?, ?)
                    """, (folder_id, sid, assign_time))
                    auto_count += 1
            logger.info(f"Auto-assigned folder {folder_id} ({subject_code}) to {auto_count} students by assigned_subjects")

        conn.commit()

        c.execute("""
            SELECT id, name, description, due_date, max_points, status,
                   created_at, updated_at, lecturer_id, subject_code
            FROM folders WHERE id = ?
        """, (folder_id,))
        row = c.fetchone()
        return dict(row)
    except sqlite3.Error as e:
        conn.rollback()
        raise HTTPException(500, f"Database error: {str(e)}")
    finally:
        conn.close()

@app.put("/api/v1/folders/{folder_id}")
def update_folder(folder_id: int, payload: FolderUpdate, current_user: dict = Depends(get_current_user)):
    """Update an assignment (folder) and optionally reassign students."""
    _ensure_lecturer(current_user)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        _ensure_folder_owner(c, folder_id, current_user["id"])

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
        # subject_code is not editable via update payload per current UI
        fields.append("updated_at = ?"); values.append(now_iso())

        if fields:
            q = "UPDATE folders SET " + ", ".join(fields) + " WHERE id = ?"
            values.append(folder_id)
            c.execute(q, values)

        # Reassign students if provided (replace set)
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
                   created_at, updated_at, lecturer_id, subject_code
            FROM folders WHERE id = ?
        """, (folder_id,))
        row = c.fetchone()
        return dict(row)
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
            JOIN folders f ON f.subject_code = s.code
            JOIN folder_assignments fa ON fa.folder_id = f.id
            WHERE fa.student_id = ?
              AND LOWER(f.status) IN ('published','active')
            ORDER BY s.code
        """, (current_user["id"],))
        rows = c.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

@app.get("/api/v1/student/folders")
def get_student_folders(current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "student":
        raise HTTPException(status_code=403, detail="Only students can access their folders")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        # Only folders assigned to this student and visible (published/active)
        c.execute("""
            SELECT f.*
            FROM folders f
            JOIN folder_assignments fa ON fa.folder_id = f.id
            WHERE fa.student_id = ?
              AND LOWER(f.status) IN ('published','active')
            ORDER BY COALESCE(f.due_date, f.created_at) ASC
        """, (current_user["id"],))
        rows = c.fetchall()
        return [dict(r) for r in rows]
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
        # Verify folder is assigned to this student and active
        c.execute("""
          SELECT f.id, f.status
          FROM folders f
          JOIN folder_assignments fa ON fa.folder_id = f.id
          WHERE f.id = ? AND fa.student_id = ?
        """, (payload.folder_id, current_user["id"]))
        frow = c.fetchone()
        if not frow:
          raise HTTPException(403, "You are not assigned to this assignment")
        status = (frow["status"] or "").lower()
        if status not in ("published", "active"):
          raise HTTPException(400, "Assignment is not open for submissions")

        now = now_iso()
        # Insert files
        new_file_ids = []
        for fl in payload.files:
            try:
                content_b64 = fl.content
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