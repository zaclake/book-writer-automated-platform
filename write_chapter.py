#!/usr/bin/env python3
"""
Write Chapter CLI
Integrated CLI for chapter generation and quality assessment.
"""

import sys
import subprocess
from pathlib import Path

def run_command(cmd: list) -> tuple[bool, str]:
    """Run a command and return success status and output."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, f"Error: {e.stderr}"

def main():
    """CLI interface for chapter generation and assessment."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Write Chapter - Integrated Generation & Assessment")
    parser.add_argument("--chapter", type=int, required=True, help="Chapter number to generate")
    parser.add_argument("--model", default="gpt-4o", help="OpenAI model to use")
    parser.add_argument("--words", type=int, default=3800, help="Target word count")
    parser.add_argument("--stage", default="complete", choices=["spike", "complete", "5-stage"], 
                       help="Generation stage")
    parser.add_argument("--skip-quality", action="store_true", help="Skip quality gate assessment")
    parser.add_argument("--output-dir", default="chapters", help="Output directory for chapters")
    
    args = parser.parse_args()
    
    # Set output path
    output_file = f"{args.output_dir}/chapter-{args.chapter:02d}.md"
    
    print(f"🚀 Writing Chapter {args.chapter}")
    print(f"📋 Configuration:")
    print(f"   Model: {args.model}")
    print(f"   Stage: {args.stage}")
    print(f"   Target words: {args.words}")
    print(f"   Output: {output_file}")
    print()
    
    # Step 1: Generate chapter
    print("📝 Generating chapter...")
    
    generation_cmd = [
        sys.executable, "system/llm_orchestrator.py",
        "--chapter", str(args.chapter),
        "--model", args.model,
        "--words", str(args.words),
        "--stage", args.stage,
        "--output", output_file
    ]
    
    success, output = run_command(generation_cmd)
    if not success:
        print(f"❌ Chapter generation failed:")
        print(output)
        return 1
    
    print("✅ Chapter generated successfully")
    print(output)
    
    # Check if chapter file exists
    if not Path(output_file).exists():
        print(f"❌ Chapter file not found: {output_file}")
        return 1
    
    # Step 2: Run quality gates (unless skipped)
    if not args.skip_quality:
        print("\n🔍 Running quality assessment...")
        
        quality_cmd = [
            sys.executable, "system/brutal_assessment_scorer.py",
            "assess", "--chapter-file", output_file,
            "--chapter-number", str(args.chapter)
        ]
        
        success, output = run_command(quality_cmd)
        if not success:
            print(f"❌ Quality assessment failed:")
            print(output)
            return 1
        
        print("✅ Quality assessment completed")
        print(output)
    
    # Step 3: Summary
    print(f"\n📊 Chapter {args.chapter} Writing Complete")
    print(f"📁 Chapter saved to: {output_file}")
    
    # Read chapter for stats
    try:
        with open(output_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        word_count = len(content.split())
        print(f"📝 Word count: {word_count}")
        
        # Check for metadata
        metadata_file = Path(output_file).with_suffix('.json')
        if metadata_file.exists():
            import json
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            if 'cost_breakdown' in metadata:
                cost = metadata['cost_breakdown']['total_cost']
                print(f"💰 Generation cost: ${cost:.4f}")
        
        print(f"\n✅ Chapter {args.chapter} ready for review!")
        
    except Exception as e:
        print(f"⚠️  Error reading chapter stats: {e}")
    
    return 0

if __name__ == "__main__":
    exit(main()) 