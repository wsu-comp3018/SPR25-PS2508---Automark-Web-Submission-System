# Backend/server/app/main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
import hashlib, sqlite3, uuid, datetime

DB_PATH = "automark.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
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
    conn.commit()
    conn.close()

def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()

def now_iso():
    return datetime.datetime.utcnow().isoformat() + "Z"

app = FastAPI(title="Automark API", version="0.2.0")

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
