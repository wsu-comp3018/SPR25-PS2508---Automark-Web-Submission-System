"Login/Register logic"

import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from db import get_db

def register_user(username, email, password, role, first_name, last_name):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ? OR email = ?", (username, email))
    if cursor.fetchone():
        raise Exception("Username or Email already exists")

    password_hash = generate_password_hash(password)
    cursor.execute("""
        INSERT INTO users (username, email, password_hash, role, first_name, last_name)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (username, email, password_hash, role, first_name, last_name))
    db.commit()

def authenticate_user(identifier, password):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ? OR email = ?", (identifier, identifier))
    row = cursor.fetchone()
    if row and check_password_hash(row["password_hash"], password):
        return row
    return None

