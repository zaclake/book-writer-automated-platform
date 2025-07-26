#!/usr/bin/env bash
set -euo pipefail

# Force flag to ensure this script is being used
echo "🚀 CUSTOM START SCRIPT EXECUTING - v2.0"
echo "Current directory at script start: $(pwd)"
echo "Script location: $0"

# Change to the directory where this script is located (repo root)
cd "$(dirname "$0")"

# Verify we're in the right place
echo "After cd to script dir: $(pwd)"
ls -la | head -10

# Set PYTHONPATH to current directory so backend.* imports work
export PYTHONPATH="$PWD"

# Set port
PORT=${PORT:-8000}

# Verify we can see the backend directory
if [ ! -d "backend" ]; then
    echo "❌ ERROR: backend directory not found in $(pwd)"
    echo "Directory contents:"
    ls -la
    exit 1
fi

# Log startup info
echo "✅ Starting from directory: $(pwd)"
echo "✅ PYTHONPATH: $PYTHONPATH"
echo "✅ Backend directory exists: $([ -d backend ] && echo 'yes' || echo 'no')"
echo "✅ Backend/main.py exists: $([ -f backend/main.py ] && echo 'yes' || echo 'no')"

# Test import before starting
echo "🔍 Testing Python import..."
python3 -c "import sys; print('Python path:', sys.path)" || echo "Python path test failed"
python3 -c "import backend.main; print('✅ Backend import successful')" || echo "❌ Backend import failed"

# Start gunicorn from repo root with backend.main:app with extended timeout for AI operations
echo "🔥 Starting gunicorn with backend.main:app (90s timeout for AI generation)"
exec gunicorn backend.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT} --timeout 90 