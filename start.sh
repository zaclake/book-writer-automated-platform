#!/usr/bin/env bash
set -euo pipefail

# Change to the directory where this script is located (repo root)
cd "$(dirname "$0")"

# Set PYTHONPATH to current directory so backend.* imports work
export PYTHONPATH="$PWD"

# Set port
PORT=${PORT:-8000}

# Verify we can see the backend directory
if [ ! -d "backend" ]; then
    echo "ERROR: backend directory not found in $(pwd)"
    ls -la
    exit 1
fi

# Log startup info
echo "Starting from directory: $(pwd)"
echo "PYTHONPATH: $PYTHONPATH"
echo "Backend directory exists: $([ -d backend ] && echo 'yes' || echo 'no')"

# Start gunicorn from repo root with backend.main:app
exec gunicorn backend.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT} 