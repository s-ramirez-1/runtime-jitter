# Force x86 Linux platform so results are consistent across
# Windows, Linux, and Apple Silicon (M1/M2/M3) Macs.
FROM --platform=linux/amd64 python:3.12-slim-bookworm

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Use locked requirements for guaranteed reproducible builds in Docker
COPY requirements-locked.txt .
RUN pip install --no-cache-dir -r requirements-locked.txt

# Copy project files
COPY . .

# Always set inside the image so batch_run.py skips venv bootstrap
ENV RUNNING_IN_DOCKER=1

# Dashboard port
EXPOSE 8501

# Default command — launch dashboard
CMD ["python", "-m", "streamlit", "run", "scripts/dashboard.py", \
     "--server.address=0.0.0.0", "--server.port=8501"]
