# AutoMark System - Docker Compose Makefile
SHELL := /bin/bash

# Service names
API_SERVICE := automark-api
SSH_SERVICE := automark-ssh
WEB_SERVICE := automark-web

# Docker Compose command
COMPOSE := docker-compose
COMPOSE_FILE := docker-compose.yml

# Default environment
ENV ?= development

.PHONY: help build up down restart logs shell-api shell-ssh clean \
        db-reset health test dev prod status volumes

help:
	@echo "AutoMark System - Docker Commands"
	@echo "================================="
	@echo ""
	@echo "🚀 Main Commands:"
	@echo "  make up           # Start all services (detached)"
	@echo "  make dev          # Start in development mode (with logs)"
	@echo "  make down         # Stop all services"
	@echo "  make restart      # Restart all services"
	@echo "  make build        # Build all containers"
	@echo ""
	@echo "📊 Monitoring:"
	@echo "  make logs         # Show all service logs"
	@echo "  make logs-api     # Show FastAPI logs"
	@echo "  make logs-ssh     # Show SSH server logs"
	@echo "  make status       # Show service status"
	@echo "  make health       # Check health of all services"
	@echo ""
	@echo "🔧 Development:"
	@echo "  make shell-api    # Open shell in FastAPI container"
	@echo "  make shell-ssh    # Open shell in SSH container"
	@echo "  make db-reset     # Reset database"
	@echo "  make test         # Run tests"
	@echo ""
	@echo "🧹 Maintenance:"
	@echo "  make clean        # Remove containers and images"
	@echo "  make volumes      # Show Docker volumes"
	@echo "  make prune        # Clean up Docker system"
	@echo ""
	@echo "🌐 URLs:"
	@echo "  Frontend:  http://localhost:3000"
	@echo "  API:       http://localhost:8000"
	@echo "  SSH:       ssh student1@localhost -p 2222"

# 🚀 Main Commands
build:
	@echo "🏗️  Building all containers..."
	$(COMPOSE) -f $(COMPOSE_FILE) build

up:
	@echo "🚀 Starting all services..."
	$(COMPOSE) -f $(COMPOSE_FILE) up -d
	@echo "✅ Services started!"
	@echo "   Frontend: http://localhost:3000"
	@echo "   API:      http://localhost:8000"
	@echo "   SSH:      ssh student1@localhost -p 2222"

dev:
	@echo "🚀 Starting development environment..."
	$(COMPOSE) -f $(COMPOSE_FILE) up --build

down:
	@echo "🛑 Stopping all services..."
	$(COMPOSE) -f $(COMPOSE_FILE) down

restart:
	@echo "🔄 Restarting all services..."
	$(COMPOSE) -f $(COMPOSE_FILE) restart

# 📊 Monitoring
logs:
	$(COMPOSE) -f $(COMPOSE_FILE) logs -f

logs-api:
	$(COMPOSE) -f $(COMPOSE_FILE) logs -f $(API_SERVICE)

logs-ssh:
	$(COMPOSE) -f $(COMPOSE_FILE) logs -f $(SSH_SERVICE)

logs-web:
	$(COMPOSE) -f $(COMPOSE_FILE) logs -f $(WEB_SERVICE)

status:
	@echo "📊 Service Status:"
	$(COMPOSE) -f $(COMPOSE_FILE) ps

health:
	@echo "🏥 Health Check:"
	@echo -n "API Health: "
	@curl -sS http://localhost:8000/health | jq -r '.status // "❌ Failed"' 2>/dev/null || echo "❌ Failed"
	@echo -n "Frontend: "
	@curl -sS http://localhost:3000 >/dev/null 2>&1 && echo "✅ OK" || echo "❌ Failed"
	@echo -n "SSH Server: "
	@nc -z localhost 2222 >/dev/null 2>&1 && echo "✅ OK" || echo "❌ Failed"

# 🔧 Development
shell-api:
	@echo "🐚 Opening shell in FastAPI container..."
	$(COMPOSE) -f $(COMPOSE_FILE) exec $(API_SERVICE) /bin/bash

shell-ssh:
	@echo "🐚 Opening shell in SSH container..."
	$(COMPOSE) -f $(COMPOSE_FILE) exec $(SSH_SERVICE) /bin/bash

db-reset:
	@echo "🗑️  Resetting database..."
	$(COMPOSE) -f $(COMPOSE_FILE) exec $(API_SERVICE) rm -f /app/data/automark.db
	$(COMPOSE) -f $(COMPOSE_FILE) restart $(API_SERVICE)
	@echo "✅ Database reset complete!"

test:
	@echo "🧪 Running tests..."
	$(COMPOSE) -f $(COMPOSE_FILE) exec $(API_SERVICE) python -m pytest tests/ -v

# 🏗️ Advanced Docker Commands
rebuild:
	@echo "🔨 Rebuilding and restarting..."
	$(COMPOSE) -f $(COMPOSE_FILE) down
	$(COMPOSE) -f $(COMPOSE_FILE) build --no-cache
	$(COMPOSE) -f $(COMPOSE_FILE) up -d

rebuild-api:
	@echo "🔨 Rebuilding FastAPI service..."
	$(COMPOSE) -f $(COMPOSE_FILE) build --no-cache $(API_SERVICE)
	$(COMPOSE) -f $(COMPOSE_FILE) up -d $(API_SERVICE)

rebuild-ssh:
	@echo "🔨 Rebuilding SSH service..."
	$(COMPOSE) -f $(COMPOSE_FILE) build --no-cache $(SSH_SERVICE)
	$(COMPOSE) -f $(COMPOSE_FILE) up -d $(SSH_SERVICE)

# 🧹 Cleanup
clean:
	@echo "🧹 Cleaning up containers and images..."
	$(COMPOSE) -f $(COMPOSE_FILE) down --rmi all --volumes --remove-orphans

clean-data:
	@echo "⚠️  WARNING: This will DELETE ALL DATA!"
	@read -p "Are you sure? (y/N): " confirm && [ "$$confirm" = "y" ] || exit 1
	$(COMPOSE) -f $(COMPOSE_FILE) down --volumes
	docker volume rm automark_automark-data automark_automark-uploads automark_automark-submissions 2>/dev/null || true

volumes:
	@echo "📦 Docker Volumes:"
	@docker volume ls | grep automark || echo "No AutoMark volumes found"

prune:
	@echo "🧹 Pruning Docker system..."
	docker system prune -f

# 🚀 Quick Start Commands
quickstart: build up
	@echo ""
	@echo "🎉 AutoMark System is ready!"
	@echo "=========================="
	@echo "Frontend:  http://localhost:3000"
	@echo "API Docs:  http://localhost:8000/docs"
	@echo "SSH Test:  ssh student1@localhost -p 2222"
	@echo ""
	@echo "Default SSH users (see Backend/docker/students.csv):"
	@cat Backend/docker/students.csv 2>/dev/null | head -5 || echo "student1,password1"

prod:
	@echo "🚀 Starting production environment..."
	ENV=production $(COMPOSE) -f $(COMPOSE_FILE) up -d
	@make health

# 📈 Monitoring and Debugging
monitor:
	@echo "📊 Monitoring all services..."
	watch -n 2 'docker-compose -f $(COMPOSE_FILE) ps && echo "" && docker stats --no-stream'

debug-api:
	@echo "🐛 Debug mode for FastAPI..."
	$(COMPOSE) -f $(COMPOSE_FILE) exec $(API_SERVICE) uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --log-level debug

# 🗄️ Database Commands
db-view:
	@echo "📊 Database Contents:"
	@docker exec $(API_SERVICE) python3 -c "import sqlite3; conn = sqlite3.connect('/app/data/automark.db'); c = conn.cursor(); print('=== USERS ==='); c.execute('SELECT id, username, email, role, first_name, last_name FROM users'); [print(f'ID: {r[0]}, User: {r[1]}, Email: {r[2]}, Role: {r[3]}, Name: {r[4]} {r[5]}') for r in c.fetchall()]; print('\\n=== SESSIONS ==='); c.execute('SELECT token, user_id, expires_at, is_active FROM sessions'); [print(f'Token: {r[0][:16]}..., UserID: {r[1]}, Expires: {r[2]}, Active: {bool(r[3])}') for r in c.fetchall()]; conn.close()"

db-schema:
	@echo "🏗️ Database Schema:"
	@docker exec $(API_SERVICE) python3 -c "import sqlite3; conn = sqlite3.connect('/app/data/automark.db'); c = conn.cursor(); c.execute('SELECT name FROM sqlite_master WHERE type=\"table\"'); [print(f'Table: {t[0]}') for t in c.fetchall()]; conn.close()"

db-copy:
	@echo "📋 Copying database to local directory..."
	@docker cp $(API_SERVICE):/app/data/automark.db ./automark-backup.db
	@echo "✅ Database copied to: ./automark-backup.db"

# 🧪 Testing Commands
test-api:
	@echo "🧪 Testing API endpoints..."
	@echo "Registering test user..."
	@curl -sS -X POST http://localhost:8000/api/v1/auth/register \
		-H "Content-Type: application/json" \
		-d '{"username":"testuser","email":"test@example.com","password":"password123","role":"student","first_name":"Test","last_name":"User"}' \
		| jq '.' || echo "❌ Registration failed"
	
test-ssh:
	@echo "🧪 Testing SSH connection..."
	@echo "Testing SSH server availability..."
	@nc -z localhost 2222 && echo "✅ SSH server is running" || echo "❌ SSH server is down"

# 📝 Documentation
docs:
	@echo "📚 Opening API documentation..."
	@which open >/dev/null 2>&1 && open http://localhost:8000/docs || echo "Visit: http://localhost:8000/docs"

info:
	@echo "ℹ️  System Information:"
	@echo "Docker version: $$(docker --version)"
	@echo "Docker Compose version: $$(docker-compose --version)"
	@echo "Services defined: $$(docker-compose -f $(COMPOSE_FILE) config --services | tr '\n' ' ')"
	@echo "Current directory: $$(pwd)"
