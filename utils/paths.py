"""
Path utilities for handling temporary project directories.
Ensures writable paths across different deployment environments.
"""
import os
from pathlib import Path


def temp_projects_root() -> Path:
    """
    Get the root directory for temporary projects.
    
    Returns a Path that is guaranteed to be writable in all deployment environments:
    - Local development: ./temp_projects (or custom via env var)
    - Railway: /app/temp_projects (or custom via env var)
    - Vercel/Lambda: /tmp/book_writer/temp_projects (or custom via env var)
    
    Returns:
        Path: The root directory for temporary projects
    """
    default_path = "/tmp/book_writer/temp_projects"
    temp_dir = os.getenv("TEMP_PROJECTS_DIR", default_path)
    
    # Ensure the directory exists
    path = Path(temp_dir)
    path.mkdir(parents=True, exist_ok=True)
    
    return path


def get_project_workspace(project_id: str) -> Path:
    """
    Get the workspace directory for a specific project.
    
    Args:
        project_id: Unique identifier for the project
        
    Returns:
        Path: The project workspace directory
    """
    return temp_projects_root() / project_id


def ensure_project_structure(project_workspace: Path) -> None:
    """
    Ensure all required project directories exist.
    
    Args:
        project_workspace: The project workspace directory
    """
    # Create main project directory
    project_workspace.mkdir(parents=True, exist_ok=True)
    
    # Create required subdirectories
    required_dirs = ["references", "chapters", "notes", ".project-state"]
    for dir_name in required_dirs:
        (project_workspace / dir_name).mkdir(exist_ok=True) 