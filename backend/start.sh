#!/bin/bash

# Default port if not provided
PORT=${PORT:-8000}

# Set PYTHONPATH to ensure backend module imports work
export PYTHONPATH="/app:$PYTHONPATH"

# Start the application with gunicorn
exec gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT 