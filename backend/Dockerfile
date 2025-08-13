FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Work from repo root inside the container
WORKDIR /app

# System dependencies required for publishing (Pandoc + XeLaTeX for PDF)
# Split update/install and add retries to mitigate transient network issues on builders
RUN apt-get update -o Acquire::Retries=5 \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
       pandoc \
       texlive-xetex \
       texlive-fonts-recommended \
       lmodern \
       ca-certificates \
       --option Acquire::Retries=5 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install backend dependencies
# Note: COPY source paths are relative to the build context (often repo root on Railway).
# Use explicit 'backend/' prefix so this works regardless of build context.
COPY backend/requirements-deploy.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy backend code and prompts explicitly from repo root
COPY backend /app/backend
COPY prompts /app/prompts

EXPOSE 8000

CMD ["sh", "-c", "gunicorn backend.main:app -w 3 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-8000} --timeout 300"]


