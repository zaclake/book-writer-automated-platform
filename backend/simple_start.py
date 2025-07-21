#!/usr/bin/env python3
"""
Minimal FastAPI app for Railway deployment testing
"""
import os
from fastapi import FastAPI
from datetime import datetime

app = FastAPI()

@app.get("/")
def root():
    return {
        "message": "Minimal backend running", 
        "timestamp": datetime.utcnow().isoformat(),
        "port": os.getenv("PORT", "8000")
    }

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port) 