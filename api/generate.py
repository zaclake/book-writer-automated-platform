import json
import os
import sys
from http.server import BaseHTTPRequestHandler
import subprocess
import tempfile
import shutil
from pathlib import Path

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            # Parse request body
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            chapter = data.get('chapter')
            words = data.get('words', 3800)
            stage = data.get('stage', 'complete')
            project_data = data.get('project_data', {})
            
            if not chapter:
                self.send_error_response(400, "Chapter number is required")
                return
            
            # Create temporary workspace
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                # Set up project structure in temp directory
                self.setup_project_structure(temp_path, project_data)
                
                # Generate chapter using the orchestrator
                result = self.generate_chapter(temp_path, chapter, words, stage)
                
                # Send response
                self.send_json_response(result)
                
        except Exception as e:
            self.send_error_response(500, f"Generation failed: {str(e)}")
    
    def setup_project_structure(self, temp_path, project_data):
        """Set up the project structure in temporary directory."""
        # Create directories
        (temp_path / "chapters").mkdir()
        (temp_path / "references").mkdir()
        (temp_path / ".project-state").mkdir()
        (temp_path / "prompts").mkdir()
        
        # Copy system files
        system_files = [
            "system/llm_orchestrator.py",
            "system/prompt_manager.py",
            "prompts/stage_1_strategic_planning.yaml",
            "prompts/stage_2_first_draft.yaml", 
            "prompts/stage_3_craft_excellence.yaml",
            "prompts/stage_4_targeted_refinement.yaml",
            "prompts/stage_5_final_integration.yaml"
        ]
        
        for file_path in system_files:
            src = Path("/var/task") / file_path
            if src.exists():
                dst = temp_path / file_path
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        
        # Create book bible if provided
        if project_data.get('book_bible'):
            with open(temp_path / "book-bible.md", 'w') as f:
                f.write(project_data['book_bible'])
        
        # Create reference files if provided
        if project_data.get('references'):
            for filename, content in project_data['references'].items():
                with open(temp_path / "references" / filename, 'w') as f:
                    f.write(content)
        
        # Create basic state files
        state_files = {
            'pattern-database.json': {},
            'quality-baselines.json': {},
            'chapter-progress.json': {},
            'session-history.json': []
        }
        
        for filename, content in state_files.items():
            with open(temp_path / ".project-state" / filename, 'w') as f:
                json.dump(content, f, indent=2)
    
    def generate_chapter(self, temp_path, chapter, words, stage):
        """Generate chapter using the orchestrator with optimized prompts."""
        try:
            # Change to temp directory
            original_cwd = os.getcwd()
            os.chdir(temp_path)
            
            # Set environment variables
            env = os.environ.copy()
            env['OPENAI_API_KEY'] = os.environ.get('OPENAI_API_KEY')
            
            # Use optimized generation approach
            return self.generate_with_optimized_prompts(temp_path, chapter, words, stage, env)
            
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Generation timed out after 5 minutes"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Generation failed: {str(e)}"
            }
        finally:
            os.chdir(original_cwd)
    
    def load_reference_files(self, temp_path):
        """Load reference files for context optimization."""
        references = []
        references_dir = temp_path / "references"
        
        if references_dir.exists():
            for ref_file in references_dir.glob("*.md"):
                try:
                    with open(ref_file, 'r') as f:
                        references.append({
                            'filename': ref_file.name,
                            'content': f.read()
                        })
                except Exception:
                    continue
        
        return references
    
    def extract_genre_from_references(self, references):
        """Extract genre information from reference files."""
        for ref in references:
            if 'style-guide' in ref['filename']:
                # Look for genre mentions in style guide
                lines = ref['content'].split('\n')
                for line in lines:
                    if 'genre' in line.lower():
                        return line.split(':')[-1].strip() if ':' in line else 'Unknown'
        return 'Unknown'
    
    def build_generation_command(self, chapter, words, stage):
        """Build the generation command."""
        if stage == '5-stage':
            return [sys.executable, "system/llm_orchestrator.py", 
                   "--chapter", str(chapter), "--words", str(words), "--stage", "5-stage"]
        elif stage == 'spike':
            return [sys.executable, "system/llm_orchestrator.py",
                   "--chapter", str(chapter), "--words", str(words), "--stage", "spike"]
        else:
            return [sys.executable, "system/llm_orchestrator.py",
                   "--chapter", str(chapter), "--words", str(words)]
    
    def generate_with_optimized_prompts(self, temp_path, chapter, words, stage, env):
        """Generate chapter with context-aware prompt optimization."""
        try:
            # Load reference files for context optimization
            references = self.load_reference_files(temp_path)
            
            # Create optimized prompts based on context
            context = {
                'chapter': chapter,
                'stage': stage,
                'targetWords': words,
                'genre': self.extract_genre_from_references(references)
            }
            
            # For now, fall back to standard generation
            # In production, this would use the optimized prompts
            cmd = self.build_generation_command(chapter, words, stage)
            
            # Execute command
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutes
                env=env
            )
            
            # Parse output
            if result.returncode == 0:
                # Try to read generated chapter
                chapter_file = temp_path / "chapters" / f"chapter-{chapter:02d}.md"
                chapter_content = ""
                if chapter_file.exists():
                    with open(chapter_file, 'r') as f:
                        chapter_content = f.read()
                
                # Try to read metadata
                metadata_file = temp_path / "chapters" / f"chapter-{chapter:02d}.json"
                metadata = {}
                if metadata_file.exists():
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                
                return {
                    "success": True,
                    "chapter": chapter,
                    "stage": stage,
                    "content": chapter_content,
                    "metadata": metadata,
                    "output": result.stdout
                }
            else:
                return {
                    "success": False,
                    "error": result.stderr or result.stdout,
                    "returncode": result.returncode
                }
                
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Generation timed out after 5 minutes"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Generation failed: {str(e)}"
            }
        finally:
            os.chdir(original_cwd)
    
    def send_json_response(self, data):
        """Send JSON response."""
        response_data = json.dumps(data).encode('utf-8')
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(response_data)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        
        self.wfile.write(response_data)
    
    def send_error_response(self, status_code, message):
        """Send error response."""
        error_data = {"error": message}
        response_data = json.dumps(error_data).encode('utf-8')
        
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(response_data)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        self.wfile.write(response_data)
    
    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers() 