#!/bin/bash

# Default port if not provided
PORT=${PORT:-8000}

# Set PYTHONPATH to parent directory so backend.* imports work
# when running from inside backend/ directory
export PYTHONPATH="$(pwd)/..":$PYTHONPATH

# Start the application with gunicorn
exec gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT 