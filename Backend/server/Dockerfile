FROM python:3.11-slim

# Set working directory
WORKDIR /app

# System deps: curl for healthcheck, subversion for svn export
# (gcc is optional; keep if some wheels need it)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    subversion \
    gcc \
 && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .

# Python deps
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Persistent dirs
RUN mkdir -p /app/data /app/uploads

# Expose API
EXPOSE 8000

# Env
ENV PYTHONPATH=/app
ENV DB_PATH=/app/data/automark.db
ENV UPLOAD_DIR=/app/uploads

# Healthcheck
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Run (dev-friendly hot reload)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
