# AutoMark Web Submission System

[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/lcU6rT0p)

A comprehensive web-based assignment submission and grading system for educational institutions. AutoMark provides both traditional SSH-based submission methods and modern web interfaces for students and lecturers.

## 🚀 Quick Start

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- Git (for cloning the repository)

### Start the System
```bash
# Clone the repository
git clone <repository-url>
cd SPR25-PS2508---Automark-Web-Submission-System

# Start all services
make quickstart
```

### Access Points
- **Frontend**: http://localhost:3000
- **API Documentation**: http://localhost:8000/docs
- **API Health Check**: http://localhost:8000/health
- **SSH Server**: `ssh student1@localhost -p 2222` (password: `password1`)

## 🛠️ Development Commands

### Main Operations
```bash
make up           # Start all services (detached)
make down         # Stop all services
make dev          # Start with live logs
make restart      # Restart all services
make build        # Build all containers
```

### Monitoring & Debugging
```bash
make status       # Show service status
make logs         # Show all service logs
make logs-api     # Show FastAPI logs only
make logs-ssh     # Show SSH server logs only
make health       # Run health checks
```

### Database Management
```bash
make db-view      # View database contents
make db-schema    # Show database structure
make db-reset     # Reset database
make db-copy      # Copy database to local file
```

### Development Tools
```bash
make shell-api    # SSH into FastAPI container
make shell-ssh    # SSH into SSH container
make test-api     # Run API tests
make test-ssh     # Test SSH connectivity
```

## 📊 API Endpoints

### Authentication
- `POST /api/v1/auth/register` - User registration (creates SSH user automatically)
- `POST /api/v1/auth/login` - User login
- `GET /api/v1/auth/session/{token}` - Session validation

### Subject Management & Enrollment
- `GET /api/v1/subjects` - List all subjects
- `POST /api/v1/enrollments` - Enroll student in subject
- `GET /api/v1/enrollments/my` - View student's enrollments
- `GET /api/v1/subjects/{subject_id}/students` - View enrolled students (lecturers)

### Assignment Management
- `GET /api/v1/folders` - List lecturer's assignment folders
- `POST /api/v1/folders` - Create assignment folder
- `PUT /api/v1/folders/{folder_id}` - Update assignment folder
- `DELETE /api/v1/folders/{folder_id}` - Delete assignment folder

### System
- `GET /health` - Health check
- `GET /api/v1/ping` - Connectivity test
- `GET /docs` - Interactive API documentation


## 🚦 Testing

### Complete Enrollment Workflow Testing

**For Development/Testing:**
The system includes a complete enrollment workflow that demonstrates how student-subject-lecturer relationships work.

#### 1. Create Test Student
```bash
# Register a new student (creates SSH user automatically)
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "teststudent",
    "email": "student@test.com",
    "password": "testpass123",
    "role": "student",
    "first_name": "Test",
    "last_name": "Student"
  }'
```

#### 2. Login Student
```bash
# Login to get session token
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "teststudent",
    "password": "testpass123"
  }'
# Save the returned token for next steps
```

#### 3. Enroll in Subjects
```bash
# Enroll in Database and Design (Autumn 2025)
curl -X POST http://localhost:8000/api/v1/enrollments \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -d '{
    "subject_code": "Comp0067",
    "semester": "AUT",
    "year": 2025
  }'

# Enroll in Object Oriented Programming (Autumn 2025)
curl -X POST http://localhost:8000/api/v1/enrollments \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -d '{
    "subject_code": "Infs8586",
    "semester": "AUT",
    "year": 2025
  }'
```

#### 4. Test SSH Access
```bash
# SSH directories are automatically created based on enrollments
ssh teststudent@localhost -p 2222
# Password: testpass123

# Once logged in, you'll see:
# - Welcome message with enrolled subjects
# - Directory structure: ~/2025/AUT/Comp0067/Assignment1-4/
# - Directory structure: ~/2025/AUT/Infs8586/Assignment1-4/
```

#### 5. View Enrollments
```bash
# Check student's enrollments via API
curl -X GET http://localhost:8000/api/v1/enrollments/my \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

### Pre-configured Test Data

The system includes pre-configured lecturers and subjects:

**Lecturers:**
- `lecturer_db` (John Smith) - teaches Comp0067 (Database and Design)
- `lecturer_prog` (Sarah Johnson) - teaches Comp0420 (Programming Techniques)  
- `lecturer_oop` (Robert Williams) - teaches Infs8586 (OOP) & Comp5055 (Software Engineering)

**Available Subjects:**
- `Comp0067` - Database and Design
- `Comp0420` - Programming Techniques
- `Infs8586` - Object Oriented Programming
- `Comp5055` - Software Engineering

### Automated Testing Script

For quick testing of the complete enrollment workflow:

```bash
# Run the automated enrollment test
./test-enrollment.sh
```

This script will:
- Create a new test student with SSH access
- Enroll them in sample subjects
- Show the automatically created directory structure
- Provide SSH login instructions

### Frontend Testing
1. Open http://localhost:3000
2. Register a new account or login
3. Navigate through student/lecturer dashboards
4. Test enrollment functionality

---

## 🏫 Production Deployment Notes

**Important:** The enrollment system above is designed for testing and demonstration. 

### Production Integration

In a production environment, the student-subject-lecturer relationships should be **automatically populated** from existing institutional systems:

1. **Student Information System (SIS) Integration**
   - Import student enrollments from university database
   - Sync with course management systems (Canvas, Blackboard, etc.)
   - Automatic semester enrollment based on academic calendar

2. **Lecturer Assignment Integration**  
   - Import teaching assignments from HR/academic systems
   - Link subjects to designated lecturers automatically
   - Handle co-teaching and substitute lecturer scenarios

3. **Subject Catalog Integration**
   - Import official course catalog with codes, names, credits
   - Maintain semester/year scheduling information
   - Handle prerequisite and enrollment capacity rules

4. **Automated Directory Provisioning**
   - SSH directories created automatically upon SIS enrollment
   - Assignment folders provisioned based on syllabus/LMS integration
   - Permissions and access control managed centrally

**The manual enrollment endpoints should be disabled or restricted to administrators in production.**

---

## 📋 SVN-Based Assignment Submission (Coming Soon)

### Workflow Overview

AutoMark uses SVN (Subversion) for assignment submissions to provide students with version control experience before transitioning to Git in advanced courses.

#### Student Workflow:
1. **SSH Login**: Students access their enrolled subjects via SSH
2. **Template Checkout**: Download assignment templates using SVN
3. **Work & Commit**: Develop solutions and commit changes
4. **Automatic Collection**: Server collects all commits as submissions

#### Example Workflow:
```bash
# 1. SSH into student account
ssh student@localhost -p 2222

# 2. Navigate to assignment directory (created automatically based on enrollments)
cd ~/2025/AUT/Comp0067/Assignment1

# 3. Checkout assignment template
svn checkout svn://automark-svn/templates/2025-AUT-Comp0067-Assignment1 .

# 4. Work on assignment
nano src/database.py
# ... develop solution ...

# 5. Submit via commit (can submit multiple times)
svn add src/new_file.py
svn commit -m "Initial submission"
svn commit -m "Fixed bug in query function"  # Update submission
```

#### Server-Side Collection:
- All student commits automatically collected to `/submissions/`
- Organized by subject, assignment, and student
- Full version history maintained for academic integrity
- Integration with grading and feedback systems

**Status**: Directory structure and enrollment system complete. SVN server integration in development.

## 📝 Data Persistence

All data is stored in Docker volumes for persistence:

- **Database**: SQLite file in `automark-data` volume
- **Uploaded Files**: Stored in `automark-uploads` volume  
- **SSH Submissions**: Stored in `automark-submissions` volume

Data persists even when containers are stopped/restarted.

## 🔍 Troubleshooting

### Common Issues

1. **Docker not running**
   ```bash
   open -a "Docker Desktop"  # macOS
   # Wait for Docker to start, then retry
   ```

2. **Ports already in use**
   ```bash
   make down  # Stop services
   # Or change ports in docker-compose.yml
   ```

3. **Database issues**
   ```bash
   make db-reset  # Reset database
   make db-view   # Check database contents
   ```

4. **Permission issues**
   ```bash
   make clean     # Clean up containers
   make build     # Rebuild containers
   ```

### Logs and Debugging
```bash
make logs          # View all logs
make logs-api      # API-specific logs
make health        # Check service health
make status        # Check container status
```



### Development Workflow
```bash
# Start development environment
make dev

# Make changes to code (hot reload enabled)
# Test changes
make test-api
make health

# View logs
make logs-api

# Reset database if needed
make db-reset
```
## Automark: Dockerized stack & sandbox E2E

### Prereqs
- Docker Desktop (with Compose v2)
- `curl` and `python3` on your host (for quick tests)

### Services
- **automark-api** (FastAPI) — persists `DB_PATH=/app/data/automark.db`, reads/writes `/app/uploads`, talks to Docker via `/var/run/docker.sock`.
- **automark-ssh** (OpenSSH) — student UNIX accounts live here, `/home` is persisted via `automark-submissions` volume.
- **automark-web** (nginx) — serves `Backend/server/static` on `:3000`, proxies `/api/*` to `automark-api:8000`.

### First-time build
```bash
docker compose build automark-ssh automark-api automark-web
docker build -t automark-sandbox:latest Backend/sandbox
Run
docker compose up -d automark-ssh automark-api automark-web
curl -s http://127.0.0.1:8000/health | python3 -m json.tool
# expect:
# { "status": "ok", "service": "automark", "version": "0.2.0" }

Quick smoke (manual)
# Register + login a lecturer
curl -s -X POST http://127.0.0.1:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"lectX","email":"lectX@ex.com","password":"Pass@123","role":"lecturer","first_name":"Lect","last_name":"X"}' | python3 -m json.tool

LECT_TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"lectX","password":"Pass@123","remember_me":true}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')

# Create a folder
curl -s -X POST http://127.0.0.1:8000/api/v1/folders \
  -H "Authorization: Bearer $LECT_TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"A1","description":"demo","status":"published","student_ids":[]}' | python3 -m json.tool

One-command endpoint to endpoint
Use the e2e.sh script below:

./e2e.sh

It will:
Ensure images are built and services are healthy
Register + login a lecturer
Create a folder
Register + login a student (and confirm the SSH user exists in automark-ssh)
Submit to the folder (enqueue sandbox)
Poll until the sandbox job finishes
Show final status/score and a quick nginx check
Troubleshooting
Name conflict (container exists already):
docker rm -f automark-api automark-ssh automark-web
DB “locked” or missing columns (e.g., feedback, graded_at, score):
bounce the API: docker compose restart automark-api
If you migrated from older DBs, re-run with fresh volumes: docker compose down -v && docker compose up -d
Sandbox didn’t run: make sure you built it:
docker build -t automark-sandbox:latest Backend/sandbox
SSH container not healthy: confirm config and that PasswordAuthentication yes is set; rebuild automark-ssh.
