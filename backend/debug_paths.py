#!/usr/bin/env python3
"""
Debug script to understand Railway deployment file structure
"""
import os
import sys
from pathlib import Path

def debug_deployment_structure():
    print("=== RAILWAY DEPLOYMENT DEBUG ===")
    print(f"Python version: {sys.version}")
    print(f"Current working directory: {os.getcwd()}")
    print(f"__file__ location: {__file__}")
    print(f"Script parent: {Path(__file__).parent}")
    
    # Check key directories
    directories_to_check = [
        "/app",
        "/app/backend",
        "/app/backend/prompts",
        "/app/backend/prompts/reference-generation",
        "/app/prompts",
        "/app/prompts/reference-generation",
        Path.cwd(),
        Path.cwd() / "prompts",
        Path.cwd() / "prompts" / "reference-generation",
        Path.cwd() / "backend" / "prompts" / "reference-generation",
        Path(__file__).parent / "prompts" / "reference-generation",
    ]
    
    for dir_path in directories_to_check:
        path = Path(dir_path)
        print(f"\nChecking: {path}")
        print(f"  Exists: {path.exists()}")
        print(f"  Is dir: {path.is_dir()}")
        
        if path.exists():
            try:
                contents = list(path.iterdir())
                print(f"  Contents: {[item.name for item in contents]}")
                
                # If this is a prompts directory, check for YAML files
                if "prompts" in str(path) or "reference-generation" in str(path):
                    yaml_files = [f for f in contents if f.name.endswith('.yaml')]
                    print(f"  YAML files: {[f.name for f in yaml_files]}")
                    
            except Exception as e:
                print(f"  Error reading directory: {e}")
    
    print("\n=== END DEBUG ===")

if __name__ == "__main__":
    debug_deployment_structure() 