FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Work from repo root inside the container
WORKDIR /app

# Install backend dependencies
COPY backend/requirements-deploy.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy entire repo (backend expects to import as 'backend.*')
COPY . /app

EXPOSE 8000

CMD ["sh", "-c", "gunicorn backend.main:app -w 3 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-8000} --timeout 300"]

