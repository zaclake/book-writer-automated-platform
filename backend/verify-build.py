#!/usr/bin/env python3
"""
Deployment verification script for the Auto-Complete Book Writing System.
Verifies that all required directories and files are present before deployment.
"""

import os
import sys
from pathlib import Path

def verify_required_files():
    """Verify all required files and directories are present."""
    print("🔍 Verifying deployment requirements...")
    
    # Get the project root (parent of backend)
    backend_dir = Path(__file__).parent
    project_root = backend_dir.parent
    
    # Required directories and files
    required_paths = [
        # Backend files
        "backend/main.py",
        "backend/requirements.txt",
        "backend/Dockerfile",
        "backend/auth_middleware.py",
        "backend/firestore_client.py",
        
        # System directory (critical for LLM orchestrator)
        "system/__init__.py",
        "system/llm_orchestrator.py",
        "system/auto_complete_book_orchestrator.py",
        
        # Utils directory
        "backend/utils/paths.py",
        "backend/utils/reference_parser.py",
        "backend/utils/reference_content_generator.py",
        
        # Config files
        "backend/env.example",
        "backend/railway.toml",
    ]
    
    missing_files = []
    present_files = []
    
    for path_str in required_paths:
        full_path = project_root / path_str
        if full_path.exists():
            present_files.append(path_str)
            print(f"✅ {path_str}")
        else:
            missing_files.append(path_str)
            print(f"❌ {path_str} - MISSING")
    
    print(f"\n📊 Summary:")
    print(f"   ✅ Present: {len(present_files)}")
    print(f"   ❌ Missing: {len(missing_files)}")
    
    if missing_files:
        print(f"\n🚨 DEPLOYMENT BLOCKED - Missing required files:")
        for file in missing_files:
            print(f"   - {file}")
        return False
    
    print(f"\n✅ All required files present - deployment can proceed")
    return True

def verify_docker_context():
    """Verify Docker build context will include all necessary files."""
    print(f"\n🐳 Verifying Docker build context...")
    
    backend_dir = Path(__file__).parent
    dockerfile_path = backend_dir / "Dockerfile"
    
    if not dockerfile_path.exists():
        print(f"❌ Dockerfile not found at {dockerfile_path}")
        return False
    
    dockerfile_content = dockerfile_path.read_text()
    
    # Check that Dockerfile copies the entire project context
    if "COPY . ." in dockerfile_content:
        print(f"✅ Dockerfile copies entire project context")
        
        # Verify system/ will be accessible from backend/
        project_root = backend_dir.parent
        system_init = project_root / "system" / "__init__.py"
        
        if system_init.exists():
            print(f"✅ system/__init__.py present - package will be accessible")
            return True
        else:
            print(f"❌ system/__init__.py missing - Python package import will fail")
            return False
    else:
        print(f"❌ Dockerfile doesn't copy full context - system/ directory may be missing")
        return False

def verify_environment_config():
    """Verify environment configuration is documented."""
    print(f"\n⚙️  Verifying environment configuration...")
    
    backend_dir = Path(__file__).parent
    env_example = backend_dir / "env.example"
    
    if not env_example.exists():
        print(f"❌ env.example not found")
        return False
    
    env_content = env_example.read_text()
    required_vars = [
        "OPENAI_API_KEY",
        "CLERK_PUBLISHABLE_KEY", 
        "CLERK_SECRET_KEY",
        "CORS_ORIGINS"
    ]
    
    missing_vars = []
    for var in required_vars:
        if var not in env_content:
            missing_vars.append(var)
    
    if missing_vars:
        print(f"❌ Missing environment variables in env.example: {missing_vars}")
        return False
    
    print(f"✅ Environment configuration documented")
    return True

def main():
    """Run all verification checks."""
    print("🚀 Auto-Complete Book Writing System - Deployment Verification\n")
    
    checks = [
        ("Required Files", verify_required_files),
        ("Docker Context", verify_docker_context), 
        ("Environment Config", verify_environment_config)
    ]
    
    failed_checks = []
    
    for check_name, check_func in checks:
        try:
            if not check_func():
                failed_checks.append(check_name)
        except Exception as e:
            print(f"❌ {check_name} check failed with error: {e}")
            failed_checks.append(check_name)
    
    print(f"\n{'='*60}")
    if failed_checks:
        print(f"🚨 DEPLOYMENT VERIFICATION FAILED")
        print(f"   Failed checks: {', '.join(failed_checks)}")
        print(f"   Please fix the issues above before deploying.")
        sys.exit(1)
    else:
        print(f"✅ DEPLOYMENT VERIFICATION PASSED")
        print(f"   All checks passed - ready for deployment!")
        sys.exit(0)

if __name__ == "__main__":
    main() 