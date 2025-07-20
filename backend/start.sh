#!/bin/bash

# Default port if not provided
PORT=${PORT:-8000}

# Start the application with gunicorn
exec gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT 