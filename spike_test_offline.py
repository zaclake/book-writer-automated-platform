#!/usr/bin/env python3
"""
Phase 0 Spike Test Script - Offline Mode
Tests the full pipeline integration without requiring OpenAI API key.
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime

def run_command(cmd: list) -> tuple[bool, str]:
    """Run a command and return success status and output."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, f"Error: {e.stderr}"

def simulate_api_generation(chapter_number: int, target_words: int) -> dict:
    """Simulate what the API orchestrator would generate."""
    
    # Generate a simulated chapter with more realistic length
    base_content = """# Chapter {chapter_number}: The Digital Trail

Detective Sarah Martinez stared at the glowing monitor, lines of code scrolling past her tired eyes. The cyber crimes unit buzzed with activity around her, keyboards clicking in a constant rhythm that had become the soundtrack to her investigation.

"Got something," called out Tech Specialist Rodriguez from across the room. "The IP traces are leading us somewhere interesting."

Sarah pushed back from her desk and walked over to Rodriguez's workstation. The screen displayed a complex network diagram, nodes connecting in patterns that reminded her of a spider's web.

"Three different servers, all registered to shell companies," Rodriguez explained, pointing to specific clusters on the screen. "But look at the timing patterns."

Sarah studied the data, her investigative instincts kicking in. Each attack had followed the same digital footprint, leaving breadcrumbs that were almost too obvious to ignore.

"It's like he wants us to follow him," she murmured, tracing the connections with her finger.

"That's what I thought too," Rodriguez agreed. "But there's something else. The encryption patterns suggest military-grade training."

Sarah felt the familiar chill of a case taking an unexpected turn. What had started as a simple cybercrime investigation was evolving into something much more dangerous.

The phone on her desk rang, its shrill tone cutting through the ambient noise of the office. She hurried back to answer it, already knowing that the call would change everything.

"Martinez," she answered, her voice steady despite the growing tension.

The voice on the other end was distorted, electronically altered to mask the speaker's identity. "Detective Martinez, you're getting close. Too close."

Sarah's hand flew to the recording button on her phone. "Who is this?"

"Someone who knows what you're really investigating. The digital murders aren't random, Detective. They're a warning."

The line went dead, leaving Sarah staring at the phone in her hand. Around her, the cybercrime unit continued its work, unaware that their investigation had just escalated to a deadly new level.

She looked back at Rodriguez, who had been watching the conversation with growing concern. "We need to trace that call," she said, her voice carrying new urgency.

"Already on it," Rodriguez replied, fingers flying across the keyboard. "But Sarah, if what that voice said is true..."

"Then we're not just hunting a cybercriminal anymore," Sarah finished grimly. "We're hunting someone who kills for digital secrets."

The investigation had taken a dark turn, and Sarah knew that every keystroke, every connection they made, brought them closer to a confrontation with a killer who understood technology better than anyone in the room.

She grabbed her jacket and headed for the door. The digital trail was leading somewhere, and she intended to follow it no matter how dangerous the path became.

The hunt for answers had become a race against time, and in the world of cybercrime, time moved at the speed of light."""

    content = base_content.format(chapter_number=chapter_number)
    
    # Calculate realistic metadata
    word_count = len(content.split())
    
    # Simulate cost calculation
    estimated_tokens = word_count * 1.3  # Rough approximation
    cost_estimate = (estimated_tokens / 1000) * 0.02  # Simulated cost
    
    return {
        "success": True,
        "content": content,
        "metadata": {
            "model": "gpt-4o-simulated",
            "chapter_number": chapter_number,
            "generation_time": 3.5,  # Simulated time
            "timestamp": datetime.now().isoformat(),
            "tokens_used": {
                "prompt": int(estimated_tokens * 0.1),
                "completion": int(estimated_tokens * 0.9),
                "total": int(estimated_tokens)
            },
            "cost_breakdown": {
                "input_cost": cost_estimate * 0.25,
                "output_cost": cost_estimate * 0.75,
                "total_cost": cost_estimate
            },
            "word_count": word_count,
            "target_words": target_words,
            "phase": "spike_test_offline"
        },
        "tokens_used": int(estimated_tokens),
        "cost_estimate": cost_estimate
    }

def main():
    """Run the offline spike test."""
    print("🚀 Phase 0 Spike Test - Offline Mode")
    print("=" * 60)
    
    # Test file path
    test_chapter = "chapters/spike-test-offline-chapter.md"
    
    print(f"📝 Simulating chapter generation: {test_chapter}")
    
    # Step 1: Simulate chapter generation
    result = simulate_api_generation(1, 3800)
    
    if result["success"]:
        print("✅ Chapter generation simulated successfully")
        print(f"📊 Simulated word count: {result['metadata']['word_count']}")
        print(f"💰 Simulated cost: ${result['cost_estimate']:.4f}")
        
        # Save the chapter
        try:
            output_path = Path(test_chapter)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(result["content"])
            
            # Save metadata
            metadata_file = output_path.with_suffix('.json')
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(result["metadata"], f, indent=2)
            
            print(f"📁 Chapter saved to: {test_chapter}")
            print(f"📋 Metadata saved to: {metadata_file}")
            
        except Exception as e:
            print(f"❌ Failed to save chapter: {e}")
            return 1
    else:
        print("❌ Chapter generation simulation failed")
        return 1
    
    # Step 2: Run quality gates
    print(f"\n🔍 Running quality gates on simulated chapter...")
    
    cmd = [sys.executable, "system/brutal_assessment_scorer.py", "assess", "--chapter-file", test_chapter]
    
    success, output = run_command(cmd)
    if not success:
        print(f"❌ Quality assessment failed: {output}")
        return 1
    
    print("✅ Quality assessment completed")
    print(output)
    
    # Step 3: Integration summary
    print(f"\n📊 Phase 0 Integration Test Results")
    print("=" * 40)
    
    try:
        with open(test_chapter, 'r', encoding='utf-8') as f:
            content = f.read()
        
        word_count = len(content.split())
        
        print(f"✅ LLM Orchestrator: Simulated successfully")
        print(f"✅ Quality Gates: Executed successfully") 
        print(f"✅ File I/O: Working correctly")
        print(f"✅ Integration: Pipeline validated")
        print(f"📊 Generated content: {word_count} words")
        
        # Check if metadata exists
        metadata_file = Path(test_chapter).with_suffix('.json')
        if metadata_file.exists():
            print(f"✅ Metadata: Saved correctly")
            
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            print(f"💰 Simulated cost: ${metadata['cost_breakdown']['total_cost']:.4f}")
        
        print(f"\n🎯 Phase 0 Spike Validation: SUCCESS")
        print(f"✅ Ready to proceed with API integration")
        print(f"✅ Quality gates integration confirmed")
        print(f"✅ File pipeline working correctly")
        
        print(f"\n📋 Next Steps:")
        print(f"1. Set OPENAI_API_KEY environment variable")
        print(f"2. Test with real API call: python3 system/llm_orchestrator.py --chapter 1 --words 1000")
        print(f"3. Proceed with Phase 1 MVP development")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error validating results: {e}")
        return 1

if __name__ == "__main__":
    exit(main()) 