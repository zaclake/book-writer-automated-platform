#!/usr/bin/env python3
"""
Thin bootstrap that starts the real application defined in `backend.main:app`.
Some hosting providers may be configured to run this file directly.
"""
import os
import uvicorn

# Import the full FastAPI application
from backend.main import app  # noqa: F401

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    # Run the canonical app location explicitly to avoid accidental import of this module
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port)