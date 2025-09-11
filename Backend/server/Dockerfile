FROM python:3.11-slim

# Faster logs / no pyc files
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1

# Set working directory
WORKDIR /app

# Install system deps (add curl for HEALTHCHECK)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
  && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy application code
COPY . .

# Create directories for data persistence
RUN mkdir -p /app/data /app/uploads

# Expose the port the app runs on
EXPOSE 8000

# Environment variables
ENV PYTHONPATH=/app
ENV DB_PATH=/app/data/automark.db
ENV UPLOAD_DIR=/app/uploads

# Health check (now works because curl is installed)
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1

# Run the application (reload is fine for dev; swap to no --reload in prod)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
