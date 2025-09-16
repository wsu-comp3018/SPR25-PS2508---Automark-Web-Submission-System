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

# SSH user management
from ssh_user_manager import create_ssh_user_for_registration

# Database path
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "automark.db"))
STATIC_DIR = BASE_DIR / "static"

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        
        # Hardcoded student information with shuffled subject assignments
        students = [
            {
                "username": "student_alice",
                "email": "alice.smith@student.automark.com",
                "password": "alicepass123",
                "first_name": "Alice",
                "last_name": "Smith",
                "assigned_subjects": ["INFS 8586", "COMP 0067"]  # OOP + Database
            },
            {
                "username": "student_bob",
                "email": "bob.johnson@student.automark.com",
                "password": "bobpass123",
                "first_name": "Bob",
                "last_name": "Johnson",
                "assigned_subjects": ["COMP 0420", "COMP 5055"]  # Programming + Software Eng
            },
            {
                "username": "student_carol",
                "email": "carol.williams@student.automark.com",
                "password": "carolpass123",
                "first_name": "Carol",
                "last_name": "Williams",
                "assigned_subjects": ["COMP 0067", "INFS 8586", "COMP 0420"]  # Database + OOP + Programming
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
                    subject_codes_str = "', '".join(student["assigned_subjects"])
                    c.execute(f"""
                        SELECT id FROM folders WHERE subject_code IN ('{subject_codes_str}')
                    """)
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
        
        # If this is a student, auto-assign them to ALL existing assignments
        if body.role == "student":
            c.execute("SELECT id FROM folders")
            folder_ids = [row[0] for row in c.fetchall()]
            assign_time = now_iso()
            for folder_id in folder_ids:
                c.execute("""
                    INSERT OR IGNORE INTO folder_assignments (folder_id, student_id, assigned_at)
                    VALUES (?, ?, ?)
                """, (folder_id, user_id, assign_time))
            conn.commit()
            print(f"✅ Auto-assigned student {body.username} to {len(folder_ids)} existing assignments")
            
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

# Folders endpoints
@app.get("/api/v1/folders")
async def get_lecturer_folders(current_user: dict = Depends(get_current_user)):
    """Get all folders created by the current lecturer with enhanced debugging"""
    if current_user["role"] != "lecturer":
        raise HTTPException(status_code=403, detail="Only lecturers can access folders")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    try:
        print(f"🔍 Getting folders for lecturer: {current_user['id']} ({current_user['username']})")
        
        # First, check what subjects this lecturer has
        c.execute("""
            SELECT code, name FROM subjects WHERE lecturer_id = ?
        """, (current_user["id"],))
        lecturer_subjects = c.fetchall()
        
        print(f"📚 Lecturer has {len(lecturer_subjects)} subjects:")
        for subject in lecturer_subjects:
            print(f"  - {subject['code']}: {subject['name']}")
        
        # Get folders with assigned student count and subject info
        c.execute("""
            SELECT f.*, 
                   s.name as subject_name,
                   COUNT(fa.student_id) as assigned_students_count
            FROM folders f
            LEFT JOIN subjects s ON f.subject_code = s.code
            LEFT JOIN folder_assignments fa ON f.id = fa.folder_id
            WHERE f.lecturer_id = ?
            GROUP BY f.id, f.name, f.description, f.due_date, f.max_points, f.status, 
                     f.created_at, f.updated_at, f.lecturer_id, f.subject_code, s.name
            ORDER BY f.created_at DESC
        """, (current_user["id"],))
        
        folders = c.fetchall()
        
        print(f"📁 Found {len(folders)} folders for lecturer:")
        for folder in folders:
            print(f"  - {folder['name']} ({folder['subject_code']}) - {folder['assigned_students_count']} students")
        
        return [dict(folder) for folder in folders]
        
    except sqlite3.Error as e:
        print(f"❌ Database error getting folders: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()

@app.post("/api/v1/folders")
async def create_folder(folder: FolderCreate, current_user: dict = Depends(get_current_user)):
    """Create a new assignment folder with enhanced error handling"""
    if current_user["role"] != "lecturer":
        raise HTTPException(status_code=403, detail="Only lecturers can create folders")
    
    # Input validation
    if not folder.name or not folder.name.strip():
        raise HTTPException(status_code=400, detail="Assignment name is required")
    
    if not folder.subject_code or not folder.subject_code.strip():
        raise HTTPException(status_code=400, detail="Subject code is required")
    
    if folder.max_points < 0:
        raise HTTPException(status_code=400, detail="Maximum points must be non-negative")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    try:
        # Start transaction
        c.execute("BEGIN TRANSACTION")
        
        # Validate that subject exists and belongs to current lecturer
        c.execute("""
            SELECT id, name FROM subjects 
            WHERE code = ? AND lecturer_id = ?
        """, (folder.subject_code.strip(), current_user["id"]))
        
        subject_result = c.fetchone()
        if not subject_result:
            raise HTTPException(
                status_code=400, 
                detail=f"Subject '{folder.subject_code}' not found or not assigned to you"
            )
        
        print(f"✅ Subject validation passed: {folder.subject_code} -> {subject_result['name']}")
        
        # Check for duplicate assignment names within the same subject
        c.execute("""
            SELECT id FROM folders 
            WHERE name = ? AND subject_code = ? AND lecturer_id = ?
        """, (folder.name.strip(), folder.subject_code.strip(), current_user["id"]))
        
        if c.fetchone():
            raise HTTPException(
                status_code=409, 
                detail=f"Assignment '{folder.name}' already exists in subject {folder.subject_code}"
            )
        
        # Create folder with enhanced data
        now = now_iso()
        c.execute("""
            INSERT INTO folders (
                name, description, due_date, max_points, status, 
                created_at, updated_at, lecturer_id, subject_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            folder.name.strip(),
            folder.description.strip() if folder.description else None,
            folder.due_date,
            folder.max_points,
            folder.status,
            now,
            now,
            current_user["id"],
            folder.subject_code.strip()
        ))
        
        folder_id = c.lastrowid
        print(f"✅ Created folder with ID: {folder_id}")
        
        # Get all active students for automatic assignment
        c.execute("SELECT id FROM users WHERE role = 'student' AND is_active = 1")
        all_students = [row[0] for row in c.fetchall()]
        
        # Assign all students to the new assignment
        if all_students:
            for student_id in all_students:
                c.execute("""
                    INSERT INTO folder_assignments (folder_id, student_id, assigned_at)
                    VALUES (?, ?, ?)
                """, (folder_id, student_id, now))
            
            print(f"✅ Auto-assigned {len(all_students)} students to assignment '{folder.name}'")
        
        # Commit transaction
        c.execute("COMMIT")
        
        # Return the complete created folder with all relationships
        c.execute("""
            SELECT f.*, 
                   s.name as subject_name,
                   COUNT(fa.student_id) as assigned_students_count
            FROM folders f
            JOIN subjects s ON f.subject_code = s.code
            LEFT JOIN folder_assignments fa ON f.id = fa.folder_id
            WHERE f.id = ?
            GROUP BY f.id
        """, (folder_id,))
        
        new_folder = dict(c.fetchone())
        
        print(f"✅ Assignment '{folder.name}' created successfully with {new_folder['assigned_students_count']} students assigned")
        
        return new_folder
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        c.execute("ROLLBACK")
        raise
    except sqlite3.IntegrityError as e:
        c.execute("ROLLBACK")
        error_msg = str(e).lower()
        if "unique constraint" in error_msg and "name" in error_msg:
            raise HTTPException(status_code=409, detail="Assignment name already exists")
        elif "foreign key constraint" in error_msg:
            raise HTTPException(status_code=400, detail="Invalid subject or lecturer reference")
        else:
            raise HTTPException(status_code=500, detail=f"Database constraint error: {str(e)}")
    except sqlite3.Error as e:
        c.execute("ROLLBACK")
        print(f"❌ Database error creating folder: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        c.execute("ROLLBACK")
        print(f"❌ Unexpected error creating folder: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
    finally:
        conn.close()

@app.put("/api/v1/folders/{folder_id}")
async def update_folder(folder_id: int, folder: FolderUpdate, current_user: dict = Depends(get_current_user)):
    """Update a folder with comprehensive validation and error handling"""
    if current_user["role"] != "lecturer":
        raise HTTPException(status_code=403, detail="Only lecturers can update folders")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    try:
        # Start transaction
        c.execute("BEGIN TRANSACTION")
        
        # Verify folder exists and belongs to current lecturer
        c.execute("""
            SELECT f.*, s.name as subject_name 
            FROM folders f
            JOIN subjects s ON f.subject_code = s.code
            WHERE f.id = ? AND f.lecturer_id = ?
        """, (folder_id, current_user["id"]))
        
        current_folder = c.fetchone()
        if not current_folder:
            raise HTTPException(status_code=404, detail="Assignment not found or access denied")
        
        current_folder = dict(current_folder)
        print(f"✅ Found assignment to update: {current_folder['name']}")
        
        # Validate updated fields
        update_fields = []
        update_values = []
        changes_made = []
        
        if folder.name is not None and folder.name.strip():
            new_name = folder.name.strip()
            if new_name != current_folder['name']:
                # Check for duplicate names in same subject
                c.execute("""
                    SELECT id FROM folders 
                    WHERE name = ? AND subject_code = ? AND lecturer_id = ? AND id != ?
                """, (new_name, current_folder['subject_code'], current_user["id"], folder_id))
                
                if c.fetchone():
                    raise HTTPException(
                        status_code=409, 
                        detail=f"Assignment '{new_name}' already exists in this subject"
                    )
                
                update_fields.append("name = ?")
                update_values.append(new_name)
                changes_made.append(f"name: '{current_folder['name']}' → '{new_name}'")
        
        if folder.description is not None:
            new_desc = folder.description.strip() if folder.description else None
            if new_desc != current_folder.get('description'):
                update_fields.append("description = ?")
                update_values.append(new_desc)
                changes_made.append(f"description updated")
        
        if folder.due_date is not None:
            if folder.due_date != current_folder.get('due_date'):
                update_fields.append("due_date = ?")
                update_values.append(folder.due_date if folder.due_date else None)
                changes_made.append(f"due date updated")
        
        if folder.max_points is not None:
            if folder.max_points < 0:
                raise HTTPException(status_code=400, detail="Maximum points cannot be negative")
            if folder.max_points != current_folder['max_points']:
                update_fields.append("max_points = ?")
                update_values.append(folder.max_points)
                changes_made.append(f"max points: {current_folder['max_points']} → {folder.max_points}")
        
        if folder.status is not None:
            valid_statuses = ['draft', 'published', 'closed']
            if folder.status not in valid_statuses:
                raise HTTPException(status_code=400, detail=f"Status must be one of: {valid_statuses}")
            if folder.status != current_folder['status']:
                update_fields.append("status = ?")
                update_values.append(folder.status)
                changes_made.append(f"status: '{current_folder['status']}' → '{folder.status}'")
        
        # Update folder if there are changes
        if update_fields:
            update_fields.append("updated_at = ?")
            update_values.append(now_iso())
            update_values.append(folder_id)
            
            c.execute(f"UPDATE folders SET {', '.join(update_fields)} WHERE id = ?", update_values)
            print(f"✅ Updated folder fields: {', '.join(changes_made)}")
        
        # Update student assignments if provided
        if folder.student_ids is not None:
            # Get current assignments
            c.execute("SELECT student_id FROM folder_assignments WHERE folder_id = ?", (folder_id,))
            current_students = {row[0] for row in c.fetchall()}
            new_students = set(folder.student_ids)
            
            # Students to add
            to_add = new_students - current_students
            # Students to remove
            to_remove = current_students - new_students
            
            if to_remove:
                c.execute(f"""
                    DELETE FROM folder_assignments 
                    WHERE folder_id = ? AND student_id IN ({','.join(['?' for _ in to_remove])})
                """, [folder_id] + list(to_remove))
                print(f"✅ Removed {len(to_remove)} student assignments")
            
            if to_add:
                # Validate that all student IDs exist and are active
                if to_add:
                    placeholders = ','.join(['?' for _ in to_add])
                    c.execute(f"""
                        SELECT id FROM users 
                        WHERE id IN ({placeholders}) AND role = 'student' AND is_active = 1
                    """, list(to_add))
                    valid_students = {row[0] for row in c.fetchall()}
                    invalid_students = to_add - valid_students
                    
                    if invalid_students:
                        raise HTTPException(
                            status_code=400, 
                            detail=f"Invalid student IDs: {list(invalid_students)}"
                        )
                
                # Add new assignments
                assign_time = now_iso()
                for student_id in to_add:
                    c.execute("""
                        INSERT INTO folder_assignments (folder_id, student_id, assigned_at)
                        VALUES (?, ?, ?)
                    """, (folder_id, student_id, assign_time))
                print(f"✅ Added {len(to_add)} student assignments")
            
            if to_add or to_remove:
                changes_made.append(f"student assignments: +{len(to_add)}, -{len(to_remove)}")
        
        # Commit transaction
        c.execute("COMMIT")
        
        # Return updated folder with full details
        c.execute("""
            SELECT f.*, 
                   s.name as subject_name,
                   COUNT(fa.student_id) as assigned_students_count
            FROM folders f
            JOIN subjects s ON f.subject_code = s.code
            LEFT JOIN folder_assignments fa ON f.id = fa.folder_id
            WHERE f.id = ?
            GROUP BY f.id
        """, (folder_id,))
        
        updated_folder = dict(c.fetchone())
        
        if changes_made:
            print(f"✅ Assignment '{updated_folder['name']}' updated successfully. Changes: {'; '.join(changes_made)}")
        else:
            print(f"✅ No changes made to assignment '{updated_folder['name']}'")
        
        return updated_folder
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        c.execute("ROLLBACK")
        raise
    except sqlite3.IntegrityError as e:
        c.execute("ROLLBACK")
        error_msg = str(e).lower()
        if "unique constraint" in error_msg and "name" in error_msg:
            raise HTTPException(status_code=409, detail="Assignment name already exists in this subject")
        elif "foreign key constraint" in error_msg:
            raise HTTPException(status_code=400, detail="Invalid reference in assignment data")
        else:
            raise HTTPException(status_code=500, detail=f"Database constraint error: {str(e)}")
    except sqlite3.Error as e:
        c.execute("ROLLBACK")
        print(f"❌ Database error updating folder {folder_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        c.execute("ROLLBACK")
        print(f"❌ Unexpected error updating folder {folder_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
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

# Additional endpoints for assignment management
@app.get("/api/v1/folders/{folder_id}/assignments")
async def get_folder_assignments(folder_id: int, current_user: dict = Depends(get_current_user)):
    """Get all student assignments for a specific folder with enhanced details"""
    if current_user["role"] != "lecturer":
        raise HTTPException(status_code=403, detail="Only lecturers can access folder assignments")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    try:
        # Verify folder belongs to current lecturer
        c.execute("SELECT lecturer_id, name FROM folders WHERE id = ?", (folder_id,))
        result = c.fetchone()
        if not result or result[0] != current_user["id"]:
            raise HTTPException(status_code=404, detail="Assignment not found or access denied")
        
        # Get all students with their assignment status and submission info
        c.execute("""
            SELECT u.id, u.username, u.first_name, u.last_name, u.email,
                   fa.assigned_at,
                   CASE WHEN fa.student_id IS NOT NULL THEN 1 ELSE 0 END as is_assigned,
                   s.submitted_at, s.status as submission_status, s.score
            FROM users u
            LEFT JOIN folder_assignments fa ON u.id = fa.student_id AND fa.folder_id = ?
            LEFT JOIN submissions s ON u.id = s.student_id AND s.folder_id = ?
            WHERE u.role = 'student' AND u.is_active = 1
            ORDER BY u.first_name, u.last_name
        """, (folder_id, folder_id))
        
        assignments = c.fetchall()
        return [dict(assignment) for assignment in assignments]
        
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()

@app.delete("/api/v1/folders/{folder_id}/assign/{student_id}")
async def unassign_student_from_folder(folder_id: int, student_id: int, current_user: dict = Depends(get_current_user)):
    """Unassign a student from a folder"""
    if current_user["role"] != "lecturer":
        raise HTTPException(status_code=403, detail="Only lecturers can unassign students")
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    try:
        # Verify folder belongs to current lecturer
        c.execute("SELECT lecturer_id FROM folders WHERE id = ?", (folder_id,))
        result = c.fetchone()
        if not result or result[0] != current_user["id"]:
            raise HTTPException(status_code=404, detail="Folder not found")
        
        # Unassign student from folder
        c.execute("""
            DELETE FROM folder_assignments 
            WHERE folder_id = ? AND student_id = ?
        """, (folder_id, student_id))
        
        if c.rowcount == 0:
            raise HTTPException(status_code=404, detail="Student assignment not found")
        
        conn.commit()
        return {"message": "Student unassigned successfully"}
        
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

# API endpoints for subjects
@app.get("/api/v1/subjects")
async def get_all_subjects(current_user: dict = Depends(get_current_user)):
    """Get all subjects with enhanced error handling and debugging"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    try:
        print(f"🔍 Getting subjects for user: {current_user['id']} ({current_user['role']})")
        
        # Get all subjects first for debugging
        c.execute("""
            SELECT s.id, s.code, s.name, s.lecturer_id, s.created_at,
                   u.first_name, u.last_name, u.username as lecturer_username,
                   u.is_active as lecturer_active
            FROM subjects s
            JOIN users u ON s.lecturer_id = u.id
            ORDER BY s.code
        """)
        
        all_subjects = c.fetchall()
        
        print(f"📊 Found {len(all_subjects)} total subjects in database:")
        for subject in all_subjects:
            print(f"  - {subject['code']}: {subject['name']} (Lecturer ID: {subject['lecturer_id']}, Active: {subject['lecturer_active']})")
        
        # Filter active subjects only
        active_subjects = [dict(subject) for subject in all_subjects if subject['lecturer_active'] == 1]
        
        print(f"✅ Returning {len(active_subjects)} active subjects")
        return active_subjects
        
    except sqlite3.Error as e:
        print(f"❌ Database error getting subjects: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        print(f"❌ Unexpected error getting subjects: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
    finally:
        conn.close()

# Enhanced folders endpoint with better debugging
@app.get("/api/v1/folders")
async def get_lecturer_folders(current_user: dict = Depends(get_current_user)):
    """Get all folders created by the current lecturer with enhanced debugging"""
    if current_user["role"] != "lecturer":
        raise HTTPException(status_code=403, detail="Only lecturers can access folders")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    try:
        print(f"🔍 Getting folders for lecturer: {current_user['id']} ({current_user['username']})")
        
        # First, check what subjects this lecturer has
        c.execute("""
            SELECT code, name FROM subjects WHERE lecturer_id = ?
        """, (current_user["id"],))
        lecturer_subjects = c.fetchall()
        
        print(f"📚 Lecturer has {len(lecturer_subjects)} subjects:")
        for subject in lecturer_subjects:
            print(f"  - {subject['code']}: {subject['name']}")
        
        # Get folders with assigned student count and subject info
        c.execute("""
            SELECT f.*, 
                   s.name as subject_name,
                   COUNT(fa.student_id) as assigned_students_count
            FROM folders f
            LEFT JOIN subjects s ON f.subject_code = s.code
            LEFT JOIN folder_assignments fa ON f.id = fa.folder_id
            WHERE f.lecturer_id = ?
            GROUP BY f.id, f.name, f.description, f.due_date, f.max_points, f.status, 
                     f.created_at, f.updated_at, f.lecturer_id, f.subject_code, s.name
            ORDER BY f.created_at DESC
        """, (current_user["id"],))
        
        folders = c.fetchall()
        
        print(f"📁 Found {len(folders)} folders for lecturer:")
        for folder in folders:
            print(f"  - {folder['name']} ({folder['subject_code']}) - {folder['assigned_students_count']} students")
        
        return [dict(folder) for folder in folders]
        
    except sqlite3.Error as e:
        print(f"❌ Database error getting folders: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()

@app.post("/api/v1/folders")
async def create_folder(folder: FolderCreate, current_user: dict = Depends(get_current_user)):
    """Create a new assignment folder with enhanced error handling"""
    if current_user["role"] != "lecturer":
        raise HTTPException(status_code=403, detail="Only lecturers can create folders")
    
    # Input validation
    if not folder.name or not folder.name.strip():
        raise HTTPException(status_code=400, detail="Assignment name is required")
    
    if not folder.subject_code or not folder.subject_code.strip():
        raise HTTPException(status_code=400, detail="Subject code is required")
    
    if folder.max_points < 0:
        raise HTTPException(status_code=400, detail="Maximum points must be non-negative")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    try:
        # Start transaction
        c.execute("BEGIN TRANSACTION")
        
        # Validate that subject exists and belongs to current lecturer
        c.execute("""
            SELECT id, name FROM subjects 
            WHERE code = ? AND lecturer_id = ?
        """, (folder.subject_code.strip(), current_user["id"]))
        
        subject_result = c.fetchone()
        if not subject_result:
            raise HTTPException(
                status_code=400, 
                detail=f"Subject '{folder.subject_code}' not found or not assigned to you"
            )
        
        print(f"✅ Subject validation passed: {folder.subject_code} -> {subject_result['name']}")
        
        # Check for duplicate assignment names within the same subject
        c.execute("""
            SELECT id FROM folders 
            WHERE name = ? AND subject_code = ? AND lecturer_id = ?
        """, (folder.name.strip(), folder.subject_code.strip(), current_user["id"]))
        
        if c.fetchone():
            raise HTTPException(
                status_code=409, 
                detail=f"Assignment '{folder.name}' already exists in subject {folder.subject_code}"
            )
        
        # Create folder with enhanced data
        now = now_iso()
        c.execute("""
            INSERT INTO folders (
                name, description, due_date, max_points, status, 
                created_at, updated_at, lecturer_id, subject_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            folder.name.strip(),
            folder.description.strip() if folder.description else None,
            folder.due_date,
            folder.max_points,
            folder.status,
            now,
            now,
            current_user["id"],
            folder.subject_code.strip()
        ))
        
        folder_id = c.lastrowid
        print(f"✅ Created folder with ID: {folder_id}")
        
        # Get all active students for automatic assignment
        c.execute("SELECT id FROM users WHERE role = 'student' AND is_active = 1")
        all_students = [row[0] for row in c.fetchall()]
        
        # Assign all students to the new assignment
        if all_students:
            for student_id in all_students:
                c.execute("""
                    INSERT INTO folder_assignments (folder_id, student_id, assigned_at)
                    VALUES (?, ?, ?)
                """, (folder_id, student_id, now))
            
            print(f"✅ Auto-assigned {len(all_students)} students to assignment '{folder.name}'")
        
        # Commit transaction
        c.execute("COMMIT")
        
        # Return the complete created folder with all relationships
        c.execute("""
            SELECT f.*, 
                   s.name as subject_name,
                   COUNT(fa.student_id) as assigned_students_count
            FROM folders f
            JOIN subjects s ON f.subject_code = s.code
            LEFT JOIN folder_assignments fa ON f.id = fa.folder_id
            WHERE f.id = ?
            GROUP BY f.id
        """, (folder_id,))
        
        new_folder = dict(c.fetchone())
        
        print(f"✅ Assignment '{folder.name}' created successfully with {new_folder['assigned_students_count']} students assigned")
        
        return new_folder
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        c.execute("ROLLBACK")
        raise
    except sqlite3.IntegrityError as e:
        c.execute("ROLLBACK")
        error_msg = str(e).lower()
        if "unique constraint" in error_msg and "name" in error_msg:
            raise HTTPException(status_code=409, detail="Assignment name already exists")
        elif "foreign key constraint" in error_msg:
            raise HTTPException(status_code=400, detail="Invalid subject or lecturer reference")
        else:
            raise HTTPException(status_code=500, detail=f"Database constraint error: {str(e)}")
    except sqlite3.Error as e:
        c.execute("ROLLBACK")
        print(f"❌ Database error creating folder: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        c.execute("ROLLBACK")
        print(f"❌ Unexpected error creating folder: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
    finally:
        conn.close()

@app.put("/api/v1/folders/{folder_id}")
async def update_folder(folder_id: int, folder: FolderUpdate, current_user: dict = Depends(get_current_user)):
    """Update a folder with comprehensive validation and error handling"""
    if current_user["role"] != "lecturer":
        raise HTTPException(status_code=403, detail="Only lecturers can update folders")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    try:
        # Start transaction
        c.execute("BEGIN TRANSACTION")
        
        # Verify folder exists and belongs to current lecturer
        c.execute("""
            SELECT f.*, s.name as subject_name 
            FROM folders f
            JOIN subjects s ON f.subject_code = s.code
            WHERE f.id = ? AND f.lecturer_id = ?
        """, (folder_id, current_user["id"]))
        
        current_folder = c.fetchone()
        if not current_folder:
            raise HTTPException(status_code=404, detail="Assignment not found or access denied")
        
        current_folder = dict(current_folder)
        print(f"✅ Found assignment to update: {current_folder['name']}")
        
        # Validate updated fields
        update_fields = []
        update_values = []
        changes_made = []
        
        if folder.name is not None and folder.name.strip():
            new_name = folder.name.strip()
            if new_name != current_folder['name']:
                # Check for duplicate names in same subject
                c.execute("""
                    SELECT id FROM folders 
                    WHERE name = ? AND subject_code = ? AND lecturer_id = ? AND id != ?
                """, (new_name, current_folder['subject_code'], current_user["id"], folder_id))
                
                if c.fetchone():
                    raise HTTPException(
                        status_code=409, 
                        detail=f"Assignment '{new_name}' already exists in this subject"
                    )
                
                update_fields.append("name = ?")
                update_values.append(new_name)
                changes_made.append(f"name: '{current_folder['name']}' → '{new_name}'")
        
        if folder.description is not None:
            new_desc = folder.description.strip() if folder.description else None
            if new_desc != current_folder.get('description'):
                update_fields.append("description = ?")
                update_values.append(new_desc)
                changes_made.append(f"description updated")
        
        if folder.due_date is not None:
            if folder.due_date != current_folder.get('due_date'):
                update_fields.append("due_date = ?")
                update_values.append(folder.due_date if folder.due_date else None)
                changes_made.append(f"due date updated")
        
        if folder.max_points is not None:
            if folder.max_points < 0:
                raise HTTPException(status_code=400, detail="Maximum points cannot be negative")
            if folder.max_points != current_folder['max_points']:
                update_fields.append("max_points = ?")
                update_values.append(folder.max_points)
                changes_made.append(f"max points: {current_folder['max_points']} → {folder.max_points}")
        
        if folder.status is not None:
            valid_statuses = ['draft', 'published', 'closed']
            if folder.status not in valid_statuses:
                raise HTTPException(status_code=400, detail=f"Status must be one of: {valid_statuses}")
            if folder.status != current_folder['status']:
                update_fields.append("status = ?")
                update_values.append(folder.status)
                changes_made.append(f"status: '{current_folder['status']}' → '{folder.status}'")
        
        # Update folder if there are changes
        if update_fields:
            update_fields.append("updated_at = ?")
            update_values.append(now_iso())
            update_values.append(folder_id)
            
            c.execute(f"UPDATE folders SET {', '.join(update_fields)} WHERE id = ?", update_values)
            print(f"✅ Updated folder fields: {', '.join(changes_made)}")
        
        # Update student assignments if provided
        if folder.student_ids is not None:
            # Get current assignments
            c.execute("SELECT student_id FROM folder_assignments WHERE folder_id = ?", (folder_id,))
            current_students = {row[0] for row in c.fetchall()}
            new_students = set(folder.student_ids)
            
            # Students to add
            to_add = new_students - current_students
            # Students to remove
            to_remove = current_students - new_students
            
            if to_remove:
                c.execute(f"""
                    DELETE FROM folder_assignments 
                    WHERE folder_id = ? AND student_id IN ({','.join(['?' for _ in to_remove])})
                """, [folder_id] + list(to_remove))
                print(f"✅ Removed {len(to_remove)} student assignments")
            
            if to_add:
                # Validate that all student IDs exist and are active
                if to_add:
                    placeholders = ','.join(['?' for _ in to_add])
                    c.execute(f"""
                        SELECT id FROM users 
                        WHERE id IN ({placeholders}) AND role = 'student' AND is_active = 1
                    """, list(to_add))
                    valid_students = {row[0] for row in c.fetchall()}
                    invalid_students = to_add - valid_students
                    
                    if invalid_students:
                        raise HTTPException(
                            status_code=400, 
                            detail=f"Invalid student IDs: {list(invalid_students)}"
                        )
                
                # Add new assignments
                assign_time = now_iso()
                for student_id in to_add:
                    c.execute("""
                        INSERT INTO folder_assignments (folder_id, student_id, assigned_at)
                        VALUES (?, ?, ?)
                    """, (folder_id, student_id, assign_time))
                print(f"✅ Added {len(to_add)} student assignments")
            
            if to_add or to_remove:
                changes_made.append(f"student assignments: +{len(to_add)}, -{len(to_remove)}")
        
        # Commit transaction
        c.execute("COMMIT")
        
        # Return updated folder with full details
        c.execute("""
            SELECT f.*, 
                   s.name as subject_name,
                   COUNT(fa.student_id) as assigned_students_count
            FROM folders f
            JOIN subjects s ON f.subject_code = s.code
            LEFT JOIN folder_assignments fa ON f.id = fa.folder_id
            WHERE f.id = ?
            GROUP BY f.id
        """, (folder_id,))
        
        updated_folder = dict(c.fetchone())
        
        if changes_made:
            print(f"✅ Assignment '{updated_folder['name']}' updated successfully. Changes: {'; '.join(changes_made)}")
        else:
            print(f"✅ No changes made to assignment '{updated_folder['name']}'")
        
        return updated_folder
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        c.execute("ROLLBACK")
        raise
    except sqlite3.IntegrityError as e:
        c.execute("ROLLBACK")
        error_msg = str(e).lower()
        if "unique constraint" in error_msg and "name" in error_msg:
            raise HTTPException(status_code=409, detail="Assignment name already exists in this subject")
        elif "foreign key constraint" in error_msg:
            raise HTTPException(status_code=400, detail="Invalid reference in assignment data")
        else:
            raise HTTPException(status_code=500, detail=f"Database constraint error: {str(e)}")
    except sqlite3.Error as e:
        c.execute("ROLLBACK")
        print(f"❌ Database error updating folder {folder_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        c.execute("ROLLBACK")
        print(f"❌ Unexpected error updating folder {folder_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
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

# Additional endpoints for assignment management
@app.get("/api/v1/folders/{folder_id}/assignments")
async def get_folder_assignments(folder_id: int, current_user: dict = Depends(get_current_user)):
    """Get all student assignments for a specific folder with enhanced details"""
    if current_user["role"] != "lecturer":
        raise HTTPException(status_code=403, detail="Only lecturers can access folder assignments")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    try:
        # Verify folder belongs to current lecturer
        c.execute("SELECT lecturer_id, name FROM folders WHERE id = ?", (folder_id,))
        result = c.fetchone()
        if not result or result[0] != current_user["id"]:
            raise HTTPException(status_code=404, detail="Assignment not found or access denied")
        
        # Get all students with their assignment status and submission info
        c.execute("""
            SELECT u.id, u.username, u.first_name, u.last_name, u.email,
                   fa.assigned_at,
                   CASE WHEN fa.student_id IS NOT NULL THEN 1 ELSE 0 END as is_assigned,
                   s.submitted_at, s.status as submission_status, s.score
            FROM users u
            LEFT JOIN folder_assignments fa ON u.id = fa.student_id AND fa.folder_id = ?
            LEFT JOIN submissions s ON u.id = s.student_id AND s.folder_id = ?
            WHERE u.role = 'student' AND u.is_active = 1
            ORDER BY u.first_name, u.last_name
        """, (folder_id, folder_id))
        
        assignments = c.fetchall()
        return [dict(assignment) for assignment in assignments]
        
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()

@app.delete("/api/v1/folders/{folder_id}/assign/{student_id}")
async def unassign_student_from_folder(folder_id: int, student_id: int, current_user: dict = Depends(get_current_user)):
    """Unassign a student from a folder"""
    if current_user["role"] != "lecturer":
        raise HTTPException(status_code=403, detail="Only lecturers can unassign students")
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    try:
        # Verify folder belongs to current lecturer
        c.execute("SELECT lecturer_id FROM folders WHERE id = ?", (folder_id,))
        result = c.fetchone()
        if not result or result[0] != current_user["id"]:
            raise HTTPException(status_code=404, detail="Folder not found")
        
        # Unassign student from folder
        c.execute("""
            DELETE FROM folder_assignments 
            WHERE folder_id = ? AND student_id = ?
        """, (folder_id, student_id))
        
        if c.rowcount == 0:
            raise HTTPException(status_code=404, detail="Student assignment not found")
        
        conn.commit()
        return {"message": "Student unassigned successfully"}
        
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

# API endpoints for subjects
@app.get("/api/v1/subjects")
async def get_all_subjects(current_user: dict = Depends(get_current_user)):
    """Get all subjects with enhanced error handling and debugging"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    try:
        print(f"🔍 Getting subjects for user: {current_user['id']} ({current_user['role']})")
        
        # Get all subjects first for debugging
        c.execute("""
            SELECT s.id, s.code, s.name, s.lecturer_id, s.created_at,
                   u.first_name, u.last_name, u.username as lecturer_username,
                   u.is_active as lecturer_active
            FROM subjects s
            JOIN users u ON s.lecturer_id = u.id
            ORDER BY s.code
        """)
        
        all_subjects = c.fetchall()
        
        print(f"📊 Found {len(all_subjects)} total subjects in database:")
        for subject in all_subjects:
            print(f"  - {subject['code']}: {subject['name']} (Lecturer ID: {subject['lecturer_id']}, Active: {subject['lecturer_active']})")
        
        # Filter active subjects only
        active_subjects = [dict(subject) for subject in all_subjects if subject['lecturer_active'] == 1]
        
        print(f"✅ Returning {len(active_subjects)} active subjects")
        return active_subjects
        
    except sqlite3.Error as e:
        print(f"❌ Database error getting subjects: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        print(f"❌ Unexpected error getting subjects: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
    finally:
        conn.close()

# Enhanced folders endpoint with better debugging
@app.get("/api/v1/folders")
async def get_lecturer_folders(current_user: dict = Depends(get_current_user)):
    """Get all folders created by the current lecturer with enhanced debugging"""
    if current_user["role"] != "lecturer":
        raise HTTPException(status_code=403, detail="Only lecturers can access folders")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    try:
        print(f"🔍 Getting folders for lecturer: {current_user['id']} ({current_user['username']})")
        
        # First, check what subjects this lecturer has
        c.execute("""
            SELECT code, name FROM subjects WHERE lecturer_id = ?
        """, (current_user["id"],))
        lecturer_subjects = c.fetchall()
        
        print(f"📚 Lecturer has {len(lecturer_subjects)} subjects:")
        for subject in lecturer_subjects:
            print(f"  - {subject['code']}: {subject['name']}")
        
        # Get folders with assigned student count and subject info
        c.execute("""
            SELECT f.*, 
                   s.name as subject_name,
                   COUNT(fa.student_id) as assigned_students_count
            FROM folders f
            LEFT JOIN subjects s ON f.subject_code = s.code
            LEFT JOIN folder_assignments fa ON f.id = fa.folder_id
            WHERE f.lecturer_id = ?
            GROUP BY f.id, f.name, f.description, f.due_date, f.max_points, f.status, 
                     f.created_at, f.updated_at, f.lecturer_id, f.subject_code, s.name
            ORDER BY f.created_at DESC
        """, (current_user["id"],))
        
        folders = c.fetchall()
        
        print(f"📁 Found {len(folders)} folders for lecturer:")
        for folder in folders:
            print(f"  - {folder['name']} ({folder['subject_code']}) - {folder['assigned_students_count']} students")
        
        return [dict(folder) for folder in folders]
        
    except sqlite3.Error as e:
        print(f"❌ Database error getting folders: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()

@app.post("/api/v1/folders")
async def create_folder(folder: FolderCreate, current_user: dict = Depends(get_current_user)):
    """Create a new assignment folder with enhanced error handling"""
    if current_user["role"] != "lecturer":
        raise HTTPException(status_code=403, detail="Only lecturers can create folders")
    
    # Input validation
    if not folder.name or not folder.name.strip():
        raise HTTPException(status_code=400, detail="Assignment name is required")