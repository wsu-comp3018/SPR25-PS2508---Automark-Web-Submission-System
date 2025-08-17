This folder contains the backend logic for the AutoMark Web Submission System. It handles grading, sandboxing and test case execution 

Backend / Server
This folder has the backend setup for our AutoMark Web Submission System. It’s the part that runs the core logic, connects to the database, and handles uploads, grading, and sandbox execution.
Folder Breakdown
app/ → main backend code (FastAPI)
main.py → starts the API (health check, auth, submissions)
ingest.py → handles uploads (SSH, SVN, or web)
runner.py → runs grading jobs inside sandbox containers
queue.py → manages job queue with Redis
models/ → database models (user, assignment, submission)
utils/ → helper functions (file handling, logging, db, security)
automark/ → runtime folders (created during execution)
incoming/ → raw uploads
submissions/ → processed submissions by term
testcases/ → instructor test cases
sandbox_runtime/ → temporary container work dirs
logs/ → execution logs
backups/ → database + submission backups
config/ → configuration files
paths.yaml → defines folder paths
settings.example.env → environment variables (DB URL, Redis URL, etc.)
alembic/ → database migrations
docker/ → Docker setup
separate Dockerfiles for API + runner
compose.yml to run API, Postgres, Redis together
scripts/ → helper scripts
backup_db.sh / restore_db.sh → manage database backups
seed_db.py → seed initial data
tests/ → pytest test cases for file handling, runner, and API endpoints
requirements.txt → Python dependencies
Makefile → shortcuts for setup, run, and tests
.gitignore → ignores runtime files and venv
README.md → this file