#!/usr/bin/env python3
"""
Research Verification Integrator
Ensures chapters include citation checklists as specified in research-tracking-system.md
"""

import re
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Tuple, Optional

class ResearchVerificationIntegrator:
    """Integrates research verification checklists into chapter generation process."""
    
    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path)
        self.state_dir = self.project_path / ".project-state"
        self.verification_log_path = self.state_dir / "research-verification-log.json"
        
        # Ensure state directory exists
        self.state_dir.mkdir(exist_ok=True)
        
        # Research element detection patterns
        self.research_patterns = {
            'technical_procedures': [
                r'\b(?:procedure|protocol|process|method|technique)\b',
                r'\b(?:operates?|functions?|works?|performs?)\b',
                r'\b(?:equipment|device|machine|instrument|tool)\b',
                r'\b(?:software|system|application|program)\b'
            ],
            'professional_roles': [
                r'\b(?:detective|officer|sergeant|lieutenant|captain|chief)\b',
                r'\b(?:doctor|nurse|physician|surgeon|pathologist|coroner)\b',
                r'\b(?:lawyer|attorney|prosecutor|judge|bailiff|clerk)\b',
                r'\b(?:analyst|specialist|technician|consultant|expert)\b',
                r'\b(?:manager|director|supervisor|administrator)\b'
            ],
            'legal_elements': [
                r'\b(?:warrant|subpoena|court|trial|hearing|deposition)\b',
                r'\b(?:evidence|testimony|witness|jury|verdict)\b',
                r'\b(?:statute|law|regulation|ordinance|code)\b',
                r'\b(?:jurisdiction|federal|state|local|municipal)\b'
            ],
            'medical_forensic': [
                r'\b(?:autopsy|pathology|forensic|toxicology|DNA)\b',
                r'\b(?:medication|drug|treatment|diagnosis|symptom)\b',
                r'\b(?:laboratory|analysis|test|examination|specimen)\b',
                r'\b(?:cause of death|time of death|manner of death)\b'
            ],
            'cultural_setting': [
                r'\b(?:neighborhood|district|community|area|region)\b',
                r'\b(?:culture|tradition|custom|practice|belief)\b',
                r'\b(?:dialect|accent|language|expression|slang)\b',
                r'\b(?:demographic|population|socioeconomic)\b'
            ],
            'geographical': [
                r'\b(?:climate|weather|temperature|precipitation)\b',
                r'\b(?:geography|terrain|landscape|topography)\b',
                r'\b(?:transportation|infrastructure|road|highway)\b',
                r'\b(?:building|architecture|structure|facility)\b'
            ]
        }
    
    def analyze_chapter_research_needs(self, chapter_text: str, chapter_number: int) -> Dict[str, Any]:
        """Analyze chapter content to determine what research verification is needed."""
        
        research_elements = {}
        verification_requirements = []
        
        # Detect research elements by category
        for category, patterns in self.research_patterns.items():
            elements = []
            for pattern in patterns:
                matches = re.findall(pattern, chapter_text, re.IGNORECASE)
                elements.extend(matches)
            
            if elements:
                research_elements[category] = list(set(elements))  # Remove duplicates
        
        # Generate verification requirements based on detected elements
        if 'technical_procedures' in research_elements:
            verification_requirements.extend([
                "Professional procedures verified by experts",
                "Technology capabilities realistic for time period",
                "Equipment and processes accurately depicted"
            ])
        
        if 'professional_roles' in research_elements:
            verification_requirements.extend([
                "Workplace hierarchies accurate",
                "Professional ethics correctly portrayed", 
                "Job responsibilities realistically depicted",
                "Industry knowledge demonstrates understanding"
            ])
        
        if 'legal_elements' in research_elements:
            verification_requirements.extend([
                "Legal procedures match actual jurisdiction",
                "Court processes accurately represented",
                "Law enforcement protocols correct"
            ])
        
        if 'medical_forensic' in research_elements:
            verification_requirements.extend([
                "Medical information medically sound",
                "Forensic procedures scientifically accurate",
                "Medical terminology used correctly"
            ])
        
        if 'cultural_setting' in research_elements:
            verification_requirements.extend([
                "Cultural practices accurately represented",
                "Dialect and expressions appropriate to region",
                "Historical context properly researched",
                "Sensitivity issues addressed appropriately"
            ])
        
        if 'geographical' in research_elements:
            verification_requirements.extend([
                "Geography and physical details correct",
                "Climate and weather patterns accurate",
                "Transportation and infrastructure realistic"
            ])
        
        return {
            'chapter_number': chapter_number,
            'research_elements': research_elements,
            'verification_requirements': list(set(verification_requirements)),  # Remove duplicates
            'requires_expert_review': len(research_elements) > 0,
            'complexity_score': len(verification_requirements),
            'categories_detected': list(research_elements.keys())
        }
    
    def generate_chapter_verification_checklist(self, analysis: Dict[str, Any]) -> str:
        """Generate verification checklist for inclusion in chapter."""
        
        chapter_number = analysis['chapter_number']
        requirements = analysis['verification_requirements']
        elements = analysis['research_elements']
        
        if not requirements:
            return "<!-- No research verification required for this chapter -->"
        
        checklist = f"""
<!-- RESEARCH VERIFICATION CHECKLIST - CHAPTER {chapter_number} -->
<!--
Generated: {datetime.now().isoformat()}
Research Complexity Score: {analysis['complexity_score']}/30
Categories Detected: {', '.join(analysis['categories_detected'])}

MANDATORY VERIFICATION REQUIREMENTS:
"""
        
        for i, requirement in enumerate(requirements, 1):
            checklist += f"{i:2d}. [ ] {requirement}\n"
        
        checklist += "\nRESEARCH ELEMENTS DETECTED:\n"
        
        for category, category_elements in elements.items():
            checklist += f"\n{category.replace('_', ' ').title()}:\n"
            for element in category_elements[:5]:  # Limit to first 5 to avoid clutter
                checklist += f"  - {element}\n"
            if len(category_elements) > 5:
                checklist += f"  ... and {len(category_elements) - 5} more\n"
        
        checklist += f"""
EXPERT CONSULTATION REQUIREMENTS:
- [ ] Minimum 2 expert consultations completed for technical areas
- [ ] Expert feedback documented and incorporated
- [ ] Expert accuracy approval obtained
- [ ] All expert recommendations addressed

SOURCE DOCUMENTATION:
- [ ] Primary sources identified and documented
- [ ] Source reliability ratings assigned
- [ ] Page references or timestamps recorded
- [ ] Fact-checking verification completed

QUALITY ASSURANCE:
- [ ] Professional accuracy verification completed
- [ ] Cultural sensitivity review completed  
- [ ] Technical terminology verified by experts
- [ ] Setting details confirmed accurate

MINIMUM RESEARCH QUALITY SCORE REQUIRED: 80/100
(Expert Consultations: 20pts, Primary Sources: 20pts, Cultural: 20pts, Professional: 20pts, Setting: 20pts)

COMPLETION STATUS: [ ] VERIFIED - All items above completed and documented
VERIFICATION DATE: ________________
EXPERT REVIEWER: __________________
-->
"""
        
        return checklist
    
    def integrate_verification_into_chapter(self, chapter_text: str, chapter_number: int) -> Tuple[str, Dict[str, Any]]:
        """Integrate verification checklist into chapter content."""
        
        # Analyze research needs
        analysis = self.analyze_chapter_research_needs(chapter_text, chapter_number)
        
        # Generate checklist
        checklist = self.generate_chapter_verification_checklist(analysis)
        
        # Determine where to insert checklist
        if analysis['requires_expert_review']:
            # Insert at end of chapter
            integrated_text = chapter_text + "\n\n" + checklist
        else:
            # Add note that no verification is needed
            integrated_text = chapter_text + "\n\n<!-- No research verification required for this chapter -->"
        
        # Log the integration
        self._log_verification_integration(analysis)
        
        return integrated_text, analysis
    
    def verify_chapter_compliance(self, chapter_text: str, chapter_number: int) -> Dict[str, Any]:
        """Verify that a chapter meets research tracking compliance requirements."""
        
        compliance_results = {
            'chapter_number': chapter_number,
            'has_verification_checklist': False,
            'checklist_location': None,
            'missing_requirements': [],
            'compliance_score': 0,
            'compliance_status': 'fail'
        }
        
        # Check if chapter has verification checklist
        checklist_pattern = r'<!--\s*RESEARCH VERIFICATION CHECKLIST.*?-->'
        checklist_match = re.search(checklist_pattern, chapter_text, re.DOTALL | re.IGNORECASE)
        
        if checklist_match:
            compliance_results['has_verification_checklist'] = True
            compliance_results['checklist_location'] = 'end'
            compliance_results['compliance_score'] += 50
        else:
            compliance_results['missing_requirements'].append('Research verification checklist not found')
        
        # Check for research elements that require verification
        analysis = self.analyze_chapter_research_needs(chapter_text, chapter_number)
        
        if analysis['requires_expert_review']:
            if compliance_results['has_verification_checklist']:
                compliance_results['compliance_score'] += 30
            else:
                compliance_results['missing_requirements'].append('Chapter contains research elements but lacks verification checklist')
            
            # Check for expert consultation documentation
            expert_patterns = [
                r'expert\s+(?:consultation|review|verification)',
                r'verified\s+by\s+expert',
                r'expert\s+feedback',
                r'professional\s+accuracy'
            ]
            
            expert_documentation_found = False
            for pattern in expert_patterns:
                if re.search(pattern, chapter_text, re.IGNORECASE):
                    expert_documentation_found = True
                    break
            
            if expert_documentation_found:
                compliance_results['compliance_score'] += 20
            else:
                compliance_results['missing_requirements'].append('No expert consultation documentation found')
        else:
            # No research elements requiring verification
            compliance_results['compliance_score'] = 100
        
        # Determine compliance status
        if compliance_results['compliance_score'] >= 90:
            compliance_results['compliance_status'] = 'excellent'
        elif compliance_results['compliance_score'] >= 80:
            compliance_results['compliance_status'] = 'good'
        elif compliance_results['compliance_score'] >= 60:
            compliance_results['compliance_status'] = 'needs_improvement'
        else:
            compliance_results['compliance_status'] = 'fail'
        
        return compliance_results
    
    def _log_verification_integration(self, analysis: Dict[str, Any]):
        """Log verification integration for tracking."""
        
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'chapter_number': analysis['chapter_number'],
            'research_elements_detected': len(analysis.get('research_elements', {})),
            'verification_requirements': len(analysis.get('verification_requirements', [])),
            'complexity_score': analysis.get('complexity_score', 0),
            'categories': analysis.get('categories_detected', [])
        }
        
        # Load existing log
        log_data = []
        if self.verification_log_path.exists():
            try:
                with open(self.verification_log_path, 'r', encoding='utf-8') as f:
                    log_data = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        
        # Add new entry
        log_data.append(log_entry)
        
        # Keep only last 100 entries
        log_data = log_data[-100:]
        
        # Save updated log
        with open(self.verification_log_path, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2)
    
    def get_verification_status_summary(self) -> Dict[str, Any]:
        """Get summary of verification integration status."""
        
        summary = {
            'total_integrations': 0,
            'chapters_requiring_verification': 0,
            'average_complexity_score': 0,
            'most_common_categories': [],
            'recent_activity': []
        }
        
        if not self.verification_log_path.exists():
            return summary
        
        try:
            with open(self.verification_log_path, 'r', encoding='utf-8') as f:
                log_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            return summary
        
        if not log_data:
            return summary
        
        summary['total_integrations'] = len(log_data)
        summary['chapters_requiring_verification'] = sum(1 for entry in log_data if entry.get('complexity_score', 0) > 0)
        
        # Calculate average complexity
        complexity_scores = [entry.get('complexity_score', 0) for entry in log_data]
        summary['average_complexity_score'] = sum(complexity_scores) / len(complexity_scores) if complexity_scores else 0
        
        # Find most common categories
        category_counts = {}
        for entry in log_data:
            for category in entry.get('categories', []):
                category_counts[category] = category_counts.get(category, 0) + 1
        
        summary['most_common_categories'] = sorted(
            category_counts.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:5]
        
        # Recent activity (last 10 entries)
        summary['recent_activity'] = log_data[-10:]
        
        return summary
    
    def run_integration_test(self) -> Dict[str, Any]:
        """Test the research verification integration system."""
        
        test_chapter = """
        Detective Sarah Martinez walked into the crime scene, her years of experience
        telling her this wasn't going to be straightforward. The forensic team was
        already processing evidence, carefully documenting each piece according to
        department protocol.
        
        "What do we have?" she asked the coroner, Dr. Williams, who was examining
        the body with practiced precision.
        
        "Preliminary examination suggests asphyxiation," he replied, pointing to the
        petechial hemorrhages in the victim's eyes. "I'll need to complete the autopsy
        to determine the exact cause and manner of death."
        
        Sarah noted the victim's position and the surrounding evidence. The forensic
        photographer was capturing every angle, ensuring the chain of custody would
        be maintained for court proceedings.
        
        She pulled out her smartphone and opened the department's case management
        software, logging the initial observations according to state regulations.
        """
        
        try:
            # Test analysis
            analysis = self.analyze_chapter_research_needs(test_chapter, 999)
            
            # Test checklist generation
            checklist = self.generate_chapter_verification_checklist(analysis)
            
            # Test integration
            integrated_text, integration_analysis = self.integrate_verification_into_chapter(test_chapter, 999)
            
            # Test compliance verification
            compliance = self.verify_chapter_compliance(integrated_text, 999)
            
            return {
                'status': 'success',
                'analysis_detected_elements': len(analysis.get('research_elements', {})),
                'analysis_requirements': len(analysis.get('verification_requirements', [])),
                'checklist_generated': len(checklist) > 100,
                'integration_successful': len(integrated_text) > len(test_chapter),
                'compliance_score': compliance.get('compliance_score', 0),
                'test_passed': all([
                    analysis.get('requires_expert_review', False),
                    len(checklist) > 100,
                    len(integrated_text) > len(test_chapter),
                    compliance.get('compliance_score', 0) > 50
                ])
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'test_passed': False
            }

# CLI Interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Research Verification Integrator")
    parser.add_argument("action", choices=["analyze", "integrate", "verify", "test", "status"], 
                       help="Action to perform")
    parser.add_argument("--chapter-file", help="Chapter file to process")
    parser.add_argument("--chapter-number", type=int, help="Chapter number")
    parser.add_argument("--text", help="Chapter text for direct processing")
    parser.add_argument("--output", help="Output file for integrated chapter")
    
    args = parser.parse_args()
    
    integrator = ResearchVerificationIntegrator()
    
    if args.action == "analyze" and (args.chapter_file or args.text) and args.chapter_number:
        if args.chapter_file:
            with open(args.chapter_file, 'r', encoding='utf-8') as f:
                chapter_text = f.read()
        else:
            chapter_text = args.text
        
        analysis = integrator.analyze_chapter_research_needs(chapter_text, args.chapter_number)
        
        print(f"Research Analysis - Chapter {args.chapter_number}")
        print(f"Requires Expert Review: {analysis['requires_expert_review']}")
        print(f"Complexity Score: {analysis['complexity_score']}/30")
        print(f"Categories Detected: {', '.join(analysis['categories_detected'])}")
        print(f"Verification Requirements: {len(analysis['verification_requirements'])}")
        
        if analysis['verification_requirements']:
            print("\nRequired Verifications:")
            for i, req in enumerate(analysis['verification_requirements'], 1):
                print(f"  {i}. {req}")
    
    elif args.action == "integrate" and (args.chapter_file or args.text) and args.chapter_number:
        if args.chapter_file:
            with open(args.chapter_file, 'r', encoding='utf-8') as f:
                chapter_text = f.read()
        else:
            chapter_text = args.text
        
        integrated_text, analysis = integrator.integrate_verification_into_chapter(chapter_text, args.chapter_number)
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(integrated_text)
            print(f"Integrated chapter saved to: {args.output}")
        else:
            print("=== INTEGRATED CHAPTER ===")
            print(integrated_text)
        
        print(f"\nIntegration Summary:")
        print(f"Research Requirements Added: {len(analysis['verification_requirements'])}")
        print(f"Expert Review Required: {analysis['requires_expert_review']}")
    
    elif args.action == "verify" and (args.chapter_file or args.text) and args.chapter_number:
        if args.chapter_file:
            with open(args.chapter_file, 'r', encoding='utf-8') as f:
                chapter_text = f.read()
        else:
            chapter_text = args.text
        
        compliance = integrator.verify_chapter_compliance(chapter_text, args.chapter_number)
        
        print(f"Compliance Verification - Chapter {args.chapter_number}")
        print(f"Status: {compliance['compliance_status'].upper()}")
        print(f"Score: {compliance['compliance_score']}/100")
        print(f"Has Verification Checklist: {compliance['has_verification_checklist']}")
        
        if compliance['missing_requirements']:
            print("\nMissing Requirements:")
            for req in compliance['missing_requirements']:
                print(f"  ❌ {req}")
    
    elif args.action == "test":
        results = integrator.run_integration_test()
        
        print("Research Verification Integration Test")
        print(f"Status: {results['status']}")
        print(f"Test Passed: {'✅ YES' if results['test_passed'] else '❌ NO'}")
        
        if results['status'] == 'success':
            print(f"Elements Detected: {results['analysis_detected_elements']}")
            print(f"Requirements Generated: {results['analysis_requirements']}")
            print(f"Checklist Generated: {'✅' if results['checklist_generated'] else '❌'}")
            print(f"Integration Successful: {'✅' if results['integration_successful'] else '❌'}")
            print(f"Compliance Score: {results['compliance_score']}/100")
        else:
            print(f"Error: {results.get('error', 'Unknown error')}")
    
    elif args.action == "status":
        status = integrator.get_verification_status_summary()
        
        print("Research Verification Status Summary")
        print(f"Total Integrations: {status['total_integrations']}")
        print(f"Chapters Requiring Verification: {status['chapters_requiring_verification']}")
        print(f"Average Complexity Score: {status['average_complexity_score']:.1f}/30")
        
        if status['most_common_categories']:
            print("\nMost Common Research Categories:")
            for category, count in status['most_common_categories']:
                print(f"  {category.replace('_', ' ').title()}: {count} chapters")
    
    else:
        print("Please provide required arguments for the specified action")
        parser.print_help() 