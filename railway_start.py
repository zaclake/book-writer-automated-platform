#!/usr/bin/env python3
"""
BULLETPROOF Railway startup script
Forces correct working directory and imports no matter what Railway does.
"""
import os
import sys
import subprocess

def main():
    # Force working directory to repo root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    # Add repo root to Python path
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    
    print(f"🚀 FORCED startup from: {os.getcwd()}")
    print(f"🔧 Python path: {sys.path[:2]}")
    print(f"📁 Backend dir exists: {os.path.exists('backend')}")
    
    # Set environment
    os.environ['PYTHONPATH'] = script_dir
    
    # Start gunicorn with absolute path
    cmd = [
        'gunicorn', 
        'backend.main:app',
        '-w', '4',
        '-k', 'uvicorn.workers.UvicornWorker',
        '--bind', f"0.0.0.0:{os.getenv('PORT', '8000')}"
    ]
    
    print(f"🔥 Executing: {' '.join(cmd)}")
    
    # Execute gunicorn
    os.execvp('gunicorn', cmd)

if __name__ == '__main__':
    main() 