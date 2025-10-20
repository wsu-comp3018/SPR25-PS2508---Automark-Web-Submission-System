FROM python:3.11-alpine

# Workdir for the job runner
WORKDIR /work

# Create a non-root user for safety
RUN adduser -D -h /work runner

# Copy the tiny runner
COPY run.py ./
RUN chown -R runner:runner /work

# Run as unprivileged user
USER runner

# Make Python quiet & unbuffered
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Default command (can be overridden)
CMD ["python", "run.py"]
