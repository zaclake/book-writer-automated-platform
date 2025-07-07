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
            
            chapter_number = data.get('chapterNumber')
            chapter_content = data.get('chapterContent')
            
            if not chapter_number or not chapter_content:
                self.send_error_response(400, "Chapter number and content are required")
                return
            
            # Create temporary workspace
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                # Set up assessment environment
                self.setup_assessment_environment(temp_path, chapter_number, chapter_content)
                
                # Run quality assessments
                results = self.run_quality_assessments(temp_path, chapter_number)
                
                # Send response
                self.send_json_response(results)
                
        except Exception as e:
            self.send_error_response(500, f"Assessment failed: {str(e)}")
    
    def setup_assessment_environment(self, temp_path, chapter_number, chapter_content):
        """Set up the assessment environment in temporary directory."""
        # Create directories
        (temp_path / "chapters").mkdir()
        (temp_path / ".project-state").mkdir()
        
        # Copy system files
        system_files = [
            "system/brutal-assessment-scorer.py",
            "system/reader-engagement-scorer.py",
            "system/quality-gate-validator.py"
        ]
        
        for file_path in system_files:
            src = Path("/var/task") / file_path
            if src.exists():
                dst = temp_path / file_path
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        
        # Create chapter file
        chapter_file = temp_path / "chapters" / f"chapter-{chapter_number:02d}.md"
        with open(chapter_file, 'w') as f:
            f.write(chapter_content)
        
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
    
    def run_quality_assessments(self, temp_path, chapter_number):
        """Run all quality assessments."""
        results = {
            "success": True,
            "chapterNumber": chapter_number,
            "assessment": {},
            "timestamp": "2024-01-01T00:00:00Z"
        }
        
        # Change to temp directory
        original_cwd = os.getcwd()
        os.chdir(temp_path)
        
        try:
            chapter_file = f"chapters/chapter-{chapter_number:02d}.md"
            
            # Run brutal assessment
            try:
                brutal_result = self.run_brutal_assessment(chapter_file)
                results["assessment"]["brutalAssessment"] = brutal_result
            except Exception as e:
                results["assessment"]["brutalAssessment"] = {
                    "error": f"Brutal assessment failed: {str(e)}",
                    "score": 0
                }
            
            # Run engagement scoring
            try:
                engagement_result = self.run_engagement_scoring(chapter_file)
                results["assessment"]["engagementScore"] = engagement_result
            except Exception as e:
                results["assessment"]["engagementScore"] = {
                    "error": f"Engagement scoring failed: {str(e)}",
                    "score": 0
                }
            
            # Run quality gates
            try:
                quality_result = self.run_quality_gates(chapter_file)
                results["assessment"]["qualityGates"] = quality_result
            except Exception as e:
                results["assessment"]["qualityGates"] = {
                    "error": f"Quality gates failed: {str(e)}",
                    "passed": 0,
                    "total": 0
                }
            
            # Calculate overall score
            results["overallScore"] = self.calculate_overall_score(results["assessment"])
            
        finally:
            os.chdir(original_cwd)
        
        return results
    
    def run_brutal_assessment(self, chapter_file):
        """Run brutal assessment scorer."""
        if not Path("system/brutal-assessment-scorer.py").exists():
            return {"error": "Brutal assessment scorer not available", "score": 0}
        
        try:
            cmd = [sys.executable, "system/brutal-assessment-scorer.py", "assess", "--chapter-file", chapter_file]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                # Parse output for score
                score = self.parse_score_from_output(result.stdout, "Overall Score:")
                return {
                    "score": score,
                    "rawOutput": result.stdout,
                    "details": {}
                }
            else:
                return {
                    "error": result.stderr or "Assessment failed",
                    "score": 0,
                    "rawOutput": result.stdout
                }
        except subprocess.TimeoutExpired:
            return {"error": "Assessment timed out", "score": 0}
    
    def run_engagement_scoring(self, chapter_file):
        """Run reader engagement scorer."""
        if not Path("system/reader-engagement-scorer.py").exists():
            return {"error": "Engagement scorer not available", "score": 0}
        
        try:
            cmd = [sys.executable, "system/reader-engagement-scorer.py", "assess", "--chapter-file", chapter_file]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                # Parse output for score
                score = self.parse_score_from_output(result.stdout, "Engagement Score:")
                return {
                    "score": score,
                    "rawOutput": result.stdout,
                    "details": {}
                }
            else:
                return {
                    "error": result.stderr or "Scoring failed",
                    "score": 0,
                    "rawOutput": result.stdout
                }
        except subprocess.TimeoutExpired:
            return {"error": "Scoring timed out", "score": 0}
    
    def run_quality_gates(self, chapter_file):
        """Run quality gate validator."""
        if not Path("system/quality-gate-validator.py").exists():
            return {"error": "Quality gate validator not available", "passed": 0, "total": 0}
        
        try:
            cmd = [sys.executable, "system/quality-gate-validator.py", "validate", "--chapter-file", chapter_file]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                # Parse output for passed/total
                passed, total = self.parse_quality_gates_from_output(result.stdout)
                return {
                    "passed": passed,
                    "total": total,
                    "passRate": total > 0 and passed / total or 0,
                    "rawOutput": result.stdout,
                    "details": {}
                }
            else:
                return {
                    "error": result.stderr or "Validation failed",
                    "passed": 0,
                    "total": 0,
                    "passRate": 0,
                    "rawOutput": result.stdout
                }
        except subprocess.TimeoutExpired:
            return {"error": "Validation timed out", "passed": 0, "total": 0}
    
    def parse_score_from_output(self, output, score_prefix):
        """Parse score from command output."""
        lines = output.split('\n')
        for line in lines:
            if score_prefix in line:
                # Extract number from line
                import re
                match = re.search(r'(\d+\.?\d*)', line)
                if match:
                    return float(match.group(1))
        return 0
    
    def parse_quality_gates_from_output(self, output):
        """Parse quality gates results from output."""
        lines = output.split('\n')
        passed = 0
        total = 0
        
        for line in lines:
            if "Passed:" in line and "Total:" in line:
                import re
                passed_match = re.search(r'Passed:\s*(\d+)', line)
                total_match = re.search(r'Total:\s*(\d+)', line)
                if passed_match:
                    passed = int(passed_match.group(1))
                if total_match:
                    total = int(total_match.group(1))
                break
        
        return passed, total
    
    def calculate_overall_score(self, assessment):
        """Calculate overall score from all assessments."""
        total_score = 0
        components = 0
        
        if "brutalAssessment" in assessment and assessment["brutalAssessment"].get("score", 0) > 0:
            total_score += assessment["brutalAssessment"]["score"]
            components += 1
        
        if "engagementScore" in assessment and assessment["engagementScore"].get("score", 0) > 0:
            total_score += assessment["engagementScore"]["score"]
            components += 1
        
        if "qualityGates" in assessment and assessment["qualityGates"].get("passRate", 0) > 0:
            total_score += assessment["qualityGates"]["passRate"] * 10  # Convert to 0-10 scale
            components += 1
        
        return components > 0 and total_score / components or 0
    
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