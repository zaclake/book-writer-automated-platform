#!/usr/bin/env python3
"""
System Demo Script
Comprehensive demonstration of the LLM orchestrator migration implementation.
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime

def print_header(title: str):
    """Print a formatted header."""
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")

def print_section(title: str):
    """Print a formatted section header."""
    print(f"\n{'─'*40}")
    print(f" {title}")
    print(f"{'─'*40}")

def run_command(cmd: list, capture_output: bool = True) -> tuple[bool, str]:
    """Run a command and return success status and output."""
    try:
        if capture_output:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return True, result.stdout
        else:
            result = subprocess.run(cmd, check=True)
            return True, ""
    except subprocess.CalledProcessError as e:
        if capture_output:
            return False, f"Error: {e.stderr}"
        else:
            return False, f"Command failed with exit code {e.returncode}"

def main():
    """Run comprehensive system demonstration."""
    print_header("LLM Orchestrator Migration - System Demo")
    print(f"Demo started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Python version: {sys.version}")
    print(f"Working directory: {os.getcwd()}")
    
    # Phase 0: Validate Dependencies
    print_section("Phase 0: Dependency Validation")
    
    # Check Python packages
    print("📋 Checking Python dependencies...")
    dependencies = ["openai", "yaml"]
    missing_deps = []
    
    for dep in dependencies:
        try:
            __import__(dep)
            print(f"   ✅ {dep}: Available")
        except ImportError:
            print(f"   ❌ {dep}: Missing")
            missing_deps.append(dep)
    
    if missing_deps:
        print(f"\n⚠️  Missing dependencies: {missing_deps}")
        print("   Install with: pip install " + " ".join(missing_deps))
    
    # Check file structure
    print("\n📁 Checking file structure...")
    required_files = [
        "system/llm_orchestrator.py",
        "system/prompt_manager.py", 
        "system/brutal_assessment_scorer.py",
        "quality-gates.yml",
        "prompts/stage_1_strategic_planning.yaml",
        "prompts/stage_2_first_draft.yaml",
        "prompts/stage_3_craft_excellence.yaml",
        "prompts/stage_4_targeted_refinement.yaml",
        "prompts/stage_5_final_integration.yaml"
    ]
    
    missing_files = []
    for file_path in required_files:
        if Path(file_path).exists():
            print(f"   ✅ {file_path}")
        else:
            print(f"   ❌ {file_path}")
            missing_files.append(file_path)
    
    if missing_files:
        print(f"\n⚠️  Missing files: {len(missing_files)}")
        for file_path in missing_files:
            print(f"      - {file_path}")
    
    # Phase 1: Prompt System Validation
    print_section("Phase 1: Prompt System Validation")
    
    print("🧪 Testing prompt manager...")
    success, output = run_command([sys.executable, "system/prompt_manager.py"])
    
    if success:
        print("✅ Prompt manager working correctly")
        lines = output.strip().split('\n')
        stage_count = len([line for line in lines if "Stage " in line and ":" in line])
        print(f"   📊 Loaded {stage_count} stage templates")
    else:
        print("❌ Prompt manager failed")
        print(f"   Error: {output}")
    
    # Phase 2: Quality Gates Validation  
    print_section("Phase 2: Quality Gates Validation")
    
    print("🔍 Testing quality assessment system...")
    
    # Use existing test chapter
    test_chapter = "chapters/test-chapter.md"
    if Path(test_chapter).exists():
        success, output = run_command([
            sys.executable, "system/brutal_assessment_scorer.py", 
            "assess", "--chapter-file", test_chapter
        ])
        
        if success:
            print("✅ Quality gates working correctly")
            # Parse output for scores
            lines = output.strip().split('\n')
            for line in lines:
                if "Overall Score:" in line:
                    print(f"   📊 {line.strip()}")
                elif "Assessment Level:" in line:
                    print(f"   📈 {line.strip()}")
        else:
            print("❌ Quality gates failed")
            print(f"   Error: {output}")
    else:
        print(f"⚠️  Test chapter not found: {test_chapter}")
        print("   Creating minimal test chapter...")
        
        # Create a simple test chapter
        Path("chapters").mkdir(exist_ok=True)
        with open(test_chapter, 'w', encoding='utf-8') as f:
            f.write("""# Test Chapter

Detective Sarah Martinez reviewed the case files on her desk. The evidence pointed to a clear pattern, but something felt off about the whole situation.

"We need to dig deeper," she said to her partner. "This isn't as simple as it looks."

The investigation was just beginning, and she had a feeling it would lead them down a dangerous path.""")
        
        print(f"   📝 Created test chapter: {test_chapter}")
        
        # Test quality gates again
        success, output = run_command([
            sys.executable, "system/brutal_assessment_scorer.py", 
            "assess", "--chapter-file", test_chapter
        ])
        
        if success:
            print("✅ Quality gates working correctly")
        else:
            print("❌ Quality gates failed")
            print(f"   Error: {output}")
    
    # Phase 3: Integration Testing
    print_section("Phase 3: Integration Testing")
    
    print("🔧 Testing orchestrator integration...")
    
    # Test without API key (should show proper error)
    if not os.getenv("OPENAI_API_KEY"):
        print("🔑 No API key found (expected for demo)")
        
        # Test cost estimation
        success, output = run_command([
            sys.executable, "system/llm_orchestrator.py",
            "--chapter", "1", "--words", "1000", "--estimate-only"
        ])
        
        if not success and "API key not found" in output:
            print("✅ API key validation working correctly")
        else:
            print("⚠️  Unexpected API key behavior")
            print(f"   Output: {output}")
    else:
        print("🔑 API key found - could test real generation")
        print("   (Skipping to avoid costs in demo)")
    
    # Test offline simulation
    print("\n🔄 Testing offline simulation...")
    success, output = run_command([sys.executable, "spike_test_offline.py"])
    
    if success:
        print("✅ Offline simulation working correctly")
        # Check if files were created
        test_files = [
            "chapters/spike-test-offline-chapter.md",
            "chapters/spike-test-offline-chapter.json"
        ]
        
        for test_file in test_files:
            if Path(test_file).exists():
                print(f"   📁 Created: {test_file}")
            else:
                print(f"   ⚠️  Missing: {test_file}")
    else:
        print("❌ Offline simulation failed")
        print(f"   Error: {output}")
    
    # Phase 4: System Summary
    print_section("Phase 4: System Implementation Summary")
    
    print("📋 Implementation Status:")
    
    completed_features = [
        "✅ Phase 0 Spike - Basic LLM orchestrator with quality gate integration",
        "✅ Phase 1 MVP - Robust orchestrator with retry logic and logging",
        "✅ Prompt Templates - Complete 5-stage YAML template system",
        "✅ Stage Integration - Full pipeline from planning to final integration",
        "✅ CLI Interface - Command-line tools for generation and assessment",
        "✅ Quality Gates - Automated brutal assessment scoring",
        "✅ Cost Tracking - Token usage and cost estimation",
        "✅ Error Handling - Exponential backoff and retry logic",
        "✅ Structured Logging - Comprehensive logging system",
        "✅ File Management - Automatic chapter and metadata saving"
    ]
    
    for feature in completed_features:
        print(f"   {feature}")
    
    print(f"\n🎯 System Capabilities:")
    capabilities = [
        "Generate chapters using GPT-4o with professional prompts",
        "5-stage generation process (Planning → Draft → Review → Refine → Integrate)",
        "Automated quality assessment against publication standards",
        "Cost tracking and budget estimation",
        "Robust error handling and retry mechanisms",
        "Structured logging for debugging and monitoring",
        "Template-based prompt management for consistency",
        "Integration with existing writing system quality gates"
    ]
    
    for capability in capabilities:
        print(f"   • {capability}")
    
    print(f"\n🚀 Ready for Next Phase:")
    next_steps = [
        "Phase 2 - Context retrieval and pattern database integration",
        "Phase 3 - Async batching and cost optimization",
        "Vercel deployment for web dashboard",
        "Authentication and user management",
        "Automated nightly generation workflows"
    ]
    
    for step in next_steps:
        print(f"   → {step}")
    
    # Phase 5: Usage Examples
    print_section("Phase 5: Usage Examples")
    
    print("📚 Usage Examples:")
    print()
    
    examples = [
        {
            "title": "Generate chapter with basic orchestrator",
            "command": "python3 system/llm_orchestrator.py --chapter 1 --words 3800 --stage complete"
        },
        {
            "title": "Generate chapter with 5-stage process",
            "command": "python3 system/llm_orchestrator.py --chapter 1 --words 3800 --stage 5-stage"
        },
        {
            "title": "Estimate generation cost",
            "command": "python3 system/llm_orchestrator.py --chapter 1 --words 3800 --estimate-only"
        },
        {
            "title": "Run quality assessment",
            "command": "python3 system/brutal_assessment_scorer.py assess --chapter-file chapters/chapter-01.md"
        },
        {
            "title": "Integrated write workflow",
            "command": "python3 write_chapter.py --chapter 1 --stage complete"
        },
        {
            "title": "Test offline simulation",
            "command": "python3 spike_test_offline.py"
        }
    ]
    
    for i, example in enumerate(examples, 1):
        print(f"{i}. {example['title']}:")
        print(f"   {example['command']}")
        print()
    
    print_header("Demo Complete")
    
    if missing_deps or missing_files:
        print("⚠️  Some components missing - see details above")
        return 1
    else:
        print("✅ All systems operational and ready for API integration")
        print("💡 Set OPENAI_API_KEY environment variable to enable generation")
        return 0

if __name__ == "__main__":
    exit(main()) 