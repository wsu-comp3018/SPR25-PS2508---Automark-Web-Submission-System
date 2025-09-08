# Backend/server/app/main.py
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
import hashlib, sqlite3, uuid, datetime
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import os
from typing import List, Optional
import json
from contextlib import asynccontextmanager


# print("Current working directory:", os.getcwd())
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
# print("STATIC_DIR exists?", STATIC_DIR.exists(), BASE_DIR)
# print("Files inside STATIC_DIR:", list(STATIC_DIR.rglob("*")))


DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "automark.db"))

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
        return {"valid": False, "message": f"Database error: {str(e)}"}
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
        # Create folder
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
            current_user["id"]
        ))
        
        folder_id = c.lastrowid
        
        # Assign students to folder
        for student_id in folder.student_ids:
            c.execute("""
                INSERT OR IGNORE INTO folder_assignments (folder_id, student_id, assigned_at)
                VALUES (?, ?, ?)
            """, (folder_id, student_id, now))
        
        conn.commit()
        
        # Return created folder
        c.execute("""
            SELECT f.*, COUNT(fa.student_id) as assigned_students_count
            FROM folders f
            LEFT JOIN folder_assignments fa ON f.id = fa.folder_id
            WHERE f.id = ?
            GROUP BY f.id
        """, (folder_id,))
        
        new_folder = dict(c.fetchone())
        return new_folder
        
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
