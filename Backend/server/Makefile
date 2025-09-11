SHELL := /bin/bash

# Prefer Python 3.11, fall back to python3 if 3.11 isn't installed
PYTHON ?= python3.11
ifeq (, $(shell command -v $(PYTHON)))
  PYTHON := python3
endif

VENV_DIR := .venv
PIP      := $(VENV_DIR)/bin/pip
PY       := $(VENV_DIR)/bin/python
UVICORN  := $(VENV_DIR)/bin/uvicorn
APP      := app.main:app
HOST     ?= 127.0.0.1
PORT     ?= 8000
API_BASE := http://$(HOST):$(PORT)

# --- Sandbox image name (can override) ---
SANDBOX_IMAGE ?= automark-sandbox:latest

# Defaults for curl helpers (override on CLI)
USER     ?= test1
EMAIL    ?= test1@example.com
PASS     ?= Passw0rd!
ROLE     ?= student
FIRST    ?= Test
LAST     ?= One
REMEMBER ?= true
TOKEN    ?=
ID       ?= 1

.PHONY: help venv install setup quickstart dev run prod health db-reset clean \
        curl-register curl-login curl-session \
        sandbox-build curl-submit curl-status sandbox-last-log sandbox-clean

help:
	@echo "make setup               # create venv + install deps"
	@echo "make quickstart          # setup then uvicorn --reload"
	@echo "make dev                 # uvicorn --reload (hot reload)"
	@echo "make run                 # uvicorn (no reload)"
	@echo "make health              # GET /health"
	@echo "make db-reset            # remove automark.db"
	@echo "make curl-register USER=... EMAIL=... PASS=... ROLE=student FIRST=... LAST=..."
	@echo "make curl-login USER=... PASS=... REMEMBER=true"
	@echo "make curl-session TOKEN=<token>"
	@echo "---- Sandbox / Submissions ----"
	@echo "make sandbox-build       # docker build Backend/sandbox -> $(SANDBOX_IMAGE)"
	@echo "make curl-submit TOKEN=...     # POST /submissions/receive"
	@echo "make curl-status TOKEN=... ID=N # GET  /submissions/{id}"
	@echo "make sandbox-last-log    # logs of the most recent sandbox container"
	@echo "make sandbox-clean       # remove all containers labeled automark=sandbox"

venv:
	$(PYTHON) -m venv $(VENV_DIR)

install: venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

setup: install
	@echo "Initializing DB by importing app..."
	$(PY) -c "import app.main as m; print('DB ready at', m.DB_PATH)"

quickstart: setup
	$(UVICORN) $(APP) --reload --host 0.0.0.0 --port $(PORT)

dev:
	$(UVICORN) $(APP) --reload --host 0.0.0.0 --port $(PORT)

run:
	$(UVICORN) $(APP) --host 0.0.0.0 --port $(PORT)

prod: run

health:
	curl -sS $(API_BASE)/health | $(PY) -m json.tool

db-reset:
	rm -f automark.db

curl-register:
	curl -sS -X POST $(API_BASE)/api/v1/auth/register \
	  -H "Content-Type: application/json" \
	  -d '{"username":"$(USER)","email":"$(EMAIL)","password":"$(PASS)","role":"$(ROLE)","first_name":"$(FIRST)","last_name":"$(LAST)"}' \
	| $(PY) -m json.tool

curl-login:
	curl -sS -X POST $(API_BASE)/api/v1/auth/login \
	  -H "Content-Type: application/json" \
	  -d '{"username":"$(USER)","password":"$(PASS)","remember_me":$(REMEMBER)}' \
	| $(PY) -m json.tool

curl-session:
	curl -sS $(API_BASE)/api/v1/auth/session/$(TOKEN) | $(PY) -m json.tool

# ---------- Sandbox & submissions ----------
# Build the sandbox image from Backend/sandbox (relative to Backend/server)
sandbox-build:
	docker build -t $(SANDBOX_IMAGE) ../sandbox

# POST /submissions/receive  (requires TOKEN from curl-login)
curl-submit:
	@if [ -z "$(TOKEN)" ]; then echo "Usage: make curl-submit TOKEN=..."; exit 1; fi
	curl -sS -H "Authorization: Bearer $(TOKEN)" -H "Content-Type: application/json" \
	  -d '{"folder_id":1,"content":"hello"}' \
	  $(API_BASE)/api/v1/submissions/receive | $(PY) -m json.tool

# GET /submissions/{id}
curl-status:
	@if [ -z "$(TOKEN)" ]; then echo "Usage: make curl-status TOKEN=... ID=N"; exit 1; fi
	curl -sS -H "Authorization: Bearer $(TOKEN)" $(API_BASE)/api/v1/submissions/$(ID) | $(PY) -m json.tool

# Logs of the last sandbox container (if kept)
sandbox-last-log:
	@cid=$$(docker ps -alq --filter "label=automark=sandbox"); \
	if [ -z "$$cid" ]; then echo "No sandbox containers found"; exit 0; fi; \
	docker logs $$cid || true

# Remove all sandbox containers (safe cleanup)
sandbox-clean:
	@ids=$$(docker ps -aq --filter "label=automark=sandbox"); \
	if [ -n "$$ids" ]; then docker rm -f $$ids; else echo "No sandbox containers to remove"; fi

clean:
	rm -rf $(VENV_DIR) __pycache__ **/__pycache__
