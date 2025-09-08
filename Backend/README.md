# Backend Login System — Implementation Design

## 1. Overview & Rationale

The backend login/authentication system provides secure, efficient user and session management for assignment submission workflows.

- **Responsibilities:**
  - Handles authentication (login, logout, JWT/session management)
  - Validates user credentials against the database (or demo CSV for initial setup)
  - Manages user data and roles (student, teacher/admin)
  - Enforces best security practices (password hashing, input validation, rate limiting)

---

## 2. Technology Stack

- **Language:** JavaScript
- **Framework:** Express.js
- **Authentication:** JSON Web Tokens (JWT)
- **Database:** SQLite (initial, easy local dev; can swap for Postgres/MySQL later)

---

## 3. API Endpoints

| Method | Endpoint         | Description                                |
|--------|------------------|--------------------------------------------|
| POST   | `/api/register`  | Register a new user                        |
| POST   | `/api/login`     | Authenticate user, returns JWT             |
| GET    | `/api/user`      | Get user details (requires JWT)            |

**Example:**
- `POST /api/login` with `{ "username": "user", "password": "pass" }` returns `{ "token": "<JWT_TOKEN>" }`.
- Authenticated routes require `Authorization: Bearer <JWT_TOKEN>` header.

---

## 4. Data Flow

1. Credentials sent from frontend to backend API.
2. Backend checks credentials (demo: CSV file; production: database).
3. On valid login, backend returns a signed JWT.
4. JWT is required on all further authenticated backend routes.

---

## 5. Dockerized Local Demo Setup

This backend supports rapid local development with Docker.  
**Note:** The included Docker setup is for initial demonstration only and uses a CSV file for user credentials, NOT a production database.

### 5.1 What’s Included

- Ubuntu-based container with SSH server
- User accounts and passwords provisioned from `students.csv`
- Each user gets a home directory and sample assignment folders
- SSH access for each user as defined in the CSV

### 5.2 Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Mac/Windows/Linux)
- This repo cloned locally

### 5.3 Initial Setup Steps

1. **Navigate to the backend Docker folder:**

```console
cd Backend/docker
```

2. **Edit users as needed:**
- Open `students.csv`. Example:
  ```
  student1,password1
  student2,password2
  teacher,adminpass
  ```

3. **Build the Docker image:**

```console
docker build -t automark-multiuser .
```

4. **Run the container:**

```console
docker run -d -p 2222:22 --name automark-multiuser automark-multiuser
```

5. **SSH into a user account from a new terminal:**

```console
ssh student1@localhost -p 2222

password: password1
```

### 5.4 Notes

- This setup is for local testing only. Do NOT use the CSV/password pattern in production.
- In future iterations, authentication will be fully database-driven and managed by the backend API.
- Each time you update `students.csv`, rebuild and restart the container.

---