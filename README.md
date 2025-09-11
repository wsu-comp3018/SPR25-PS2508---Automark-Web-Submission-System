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
- `POST /api/v1/auth/register` - User registration
- `POST /api/v1/auth/login` - User login
- `GET /api/v1/auth/session/{token}` - Session validation

### System
- `GET /health` - Health check
- `GET /api/v1/ping` - Connectivity test
- `GET /docs` - Interactive API documentation

### Coming Soon
- Assignment management endpoints
- File upload/download endpoints
- Grading and feedback endpoints
- Submission tracking endpoints


## 🚦 Testing

### API Testing
```bash
# Test user registration
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "email": "test@example.com",
    "password": "password123",
    "role": "student",
    "first_name": "Test",
    "last_name": "User"
  }'

# Test user login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "password123"
  }'
```

### SSH Testing
```bash
# Test SSH connection
ssh student1@localhost -p 2222
# Password: password1
```

### Frontend Testing
1. Open http://localhost:3000
2. Register a new account or login
3. Navigate through student/lecturer dashboards
4. Test file upload functionality

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

# Build & start API + SSH + Web
docker compose up -d --build automark-api automark-ssh automark-web

# Health
curl -s http://127.0.0.1:8000/health | python3 -m json.tool

# Register/login smoke
curl -s -X POST http://127.0.0.1:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"smoke","email":"smoke@ex.com","password":"Secret2!","role":"student","first_name":"Smoke","last_name":"Test"}' | python3 -m json.tool

TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"smoke","password":"Secret2!","remember_me":true}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')

RESP=$(curl -s -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"folder_id":1,"content":"compose-test"}' \
  http://127.0.0.1:8000/api/v1/submissions/receive)

echo "$RESP" | python3 -m json.tool
SID=$(python3 -c 'import sys,json; print(json.load(sys.stdin)["submission_id"])' <<<"$RESP")
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/v1/submissions/$SID | python3 -m json.tool

# Optionally check API logs for sandbox line(s)
docker logs automark-api --since 5m | egrep 'sandbox|submission' || true

