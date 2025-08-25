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

.PHONY: help venv install setup quickstart dev run prod health db-reset clean \
        curl-register curl-login curl-session

help:
	@echo "make setup        # create venv + install deps"
	@echo "make quickstart   # setup then run uvicorn --reload"
	@echo "make dev          # run uvicorn --reload (hot reload)"
	@echo "make run          # run uvicorn (no reload)"
	@echo "make health       # GET /health"
	@echo "make db-reset     # remove automark.db"
	@echo "make curl-register USER=... EMAIL=... PASS=... ROLE=student FIRST=... LAST=..."
	@echo "make curl-login   USER=... PASS=... REMEMBER=true"
	@echo "make curl-session TOKEN=<token>"

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

clean:
	rm -rf $(VENV_DIR) __pycache__ **/__pycache__
