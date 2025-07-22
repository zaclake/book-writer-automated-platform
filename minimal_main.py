#!/usr/bin/env python3
"""
Minimal FastAPI backend with essential book-bible functionality
No complex dependencies, no Firebase, no auth - just the core functionality
"""
import os
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="Book Writer Backend", version="2.0.0")

class BookBibleInitializeRequest(BaseModel):
    project_id: str
    content: str

@app.get("/")
def root():
    return {
        "message": "Book Writer Backend v2.0 - NEW DEPLOYMENT SUCCESS",
        "timestamp": datetime.utcnow().isoformat(),
        "status": "running"
    }

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "2.0.0"
    }

@app.post("/book-bible/initialize")
def initialize_book_bible(request: BookBibleInitializeRequest):
    """
    Initialize a project from a book bible content.
    Minimal version that just saves the file and returns success.
    """
    try:
        # Create temp_projects directory if it doesn't exist
        temp_projects_dir = Path("temp_projects")
        temp_projects_dir.mkdir(exist_ok=True)
        
        # Create project workspace
        project_workspace = temp_projects_dir / request.project_id
        project_workspace.mkdir(exist_ok=True)
        
        # Save book bible content
        book_bible_path = project_workspace / "book-bible.md"
        with open(book_bible_path, 'w', encoding='utf-8') as f:
            f.write(request.content)
        
        return {
            "success": True,
            "project_id": request.project_id,
            "message": "Project initialized successfully",
            "workspace_path": str(project_workspace),
            "book_bible_path": str(book_bible_path)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port) 