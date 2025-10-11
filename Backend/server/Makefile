# Backend/server/Makefile
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

# Defaults for curl helpers (override on CLI)
USER     ?= test1
EMAIL    ?= test1@example.com
PASS     ?= Passw0rd!
ROLE     ?= student
FIRST    ?= Test
LAST     ?= One
REMEMBER ?= true
TOKEN    ?=

# Optional convenience creds for quick flows
L_USER   ?= lect1
L_PASS   ?= Pass@123
S_USER   ?= stud1
S_PASS   ?= Secret2!
FOLDER_NAME   ?= A1
FOLDER_DESC   ?= test
FOLDER_STATUS ?= published
FOLDER_ID     ?= 1
CONTENT       ?= smoke-test
SUBMISSION_ID ?= 1

.PHONY: help venv install setup quickstart dev run prod health db-reset clean \
        curl-register curl-login curl-session \
        login-lect-save login-stud-save \
        curl-folder-create curl-submit curl-poll

help:
	@echo "make setup             # create venv + install deps"
	@echo "make quickstart        # setup then run uvicorn --reload"
	@echo "make dev               # run uvicorn --reload (hot reload)"
	@echo "make run               # run uvicorn (no reload)"
	@echo "make health            # GET /health"
	@echo "make db-reset          # remove automark.db"
	@echo "make curl-register     USER=... EMAIL=... PASS=... ROLE=student FIRST=... LAST=..."
	@echo "make curl-login        USER=... PASS=... REMEMBER=true"
	@echo "make curl-session      TOKEN=<token>"
	@echo "make login-lect-save   # login lecturer (L_USER/L_PASS) -> .lect_token"
	@echo "make login-stud-save   # login student (S_USER/S_PASS)  -> .stud_token"
	@echo "make curl-folder-create# create folder (uses .lect_token)"
	@echo "make curl-submit       # student submit (uses .stud_token)"
	@echo "make curl-poll         # poll submission id (uses .stud_token)"

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
	curl -sS http://$(HOST):$(PORT)/health | $(PY) -m json.tool

db-reset:
	rm -f automark.db

curl-register:
	curl -sS -X POST http://$(HOST):$(PORT)/api/v1/auth/register \
	  -H "Content-Type: application/json" \
	  -d '{"username":"$(USER)","email":"$(EMAIL)","password":"$(PASS)","role":"$(ROLE)","first_name":"$(FIRST)","last_name":"$(LAST)"}' \
	| $(PY) -m json.tool

curl-login:
	curl -sS -X POST http://$(HOST):$(PORT)/api/v1/auth/login \
	  -H "Content-Type: application/json" \
	  -d '{"username":"$(USER)","password":"$(PASS)","remember_me":$(REMEMBER)}' \
	| $(PY) -m json.tool

curl-session:
	curl -sS http://$(HOST):$(PORT)/api/v1/auth/session/$(TOKEN) \
	| $(PY) -m json.tool

# ----------- Convenience: saved tokens for auth flows -----------
login-lect-save:
	@echo "Getting lecturer token -> .lect_token"
	@curl -sS -X POST http://$(HOST):$(PORT)/api/v1/auth/login \
	  -H "Content-Type: application/json" \
	  -d '{"username":"$(L_USER)","password":"$(L_PASS)","remember_me":$(REMEMBER)}' \
	| $(PY) -c 'import sys,json; print(json.load(sys.stdin)["token"])' > .lect_token && echo "Saved .lect_token"

login-stud-save:
	@echo "Getting student token -> .stud_token"
	@curl -sS -X POST http://$(HOST):$(PORT)/api/v1/auth/login \
	  -H "Content-Type: application/json" \
	  -d '{"username":"$(S_USER)","password":"$(S_PASS)","remember_me":$(REMEMBER)}' \
	| $(PY) -c 'import sys,json; print(json.load(sys.stdin)["token"])' > .stud_token && echo "Saved .stud_token"

# ----------- Lecturer: create folder -----------
curl-folder-create:
	@TOKEN=$$(cat .lect_token); \
	curl -sS -X POST http://$(HOST):$(PORT)/api/v1/folders \
	  -H "Authorization: Bearer $$TOKEN" -H "Content-Type: application/json" \
	  -d '{"name":"$(FOLDER_NAME)","description":"$(FOLDER_DESC)","status":"$(FOLDER_STATUS)","student_ids":[]}' \
	| $(PY) -m json.tool

# ----------- Student: submit & poll -----------
curl-submit:
	@TOKEN=$$(cat .stud_token); \
	curl -sS -X POST http://$(HOST):$(PORT)/api/v1/submissions/receive \
	  -H "Authorization: Bearer $$TOKEN" -H "Content-Type: application/json" \
	  -d '{"folder_id":$(FOLDER_ID),"content":"$(CONTENT)"}' \
	| tee .submission_resp.json | $(PY) -m json.tool

curl-poll:
	@TOKEN=$$(cat .stud_token); \
	curl -sS http://$(HOST):$(PORT)/api/v1/submissions/$(SUBMISSION_ID) \
	  -H "Authorization: Bearer $$TOKEN" \
	| $(PY) -m json.tool

clean:
	rm -rf $(VENV_DIR) __pycache__ **/__pycache__
