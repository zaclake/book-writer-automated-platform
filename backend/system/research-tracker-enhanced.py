#!/usr/bin/env python3
"""
Enhanced Research Tracker
Automated citation logging and verification checklist generator for chapters.
"""

import json
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict

@dataclass
class Citation:
    """Represents a research citation."""
    id: str
    type: str  # expert_interview, primary_source, field_research, etc.
    title: str
    author: str
    date: str
    page_reference: str
    reliability_score: float
    verification_status: str
    chapter_usage: List[str]

@dataclass
class ResearchVerification:
    """Represents verification status for a research element."""
    element_type: str
    description: str
    source_citations: List[str]
    expert_verified: bool
    verification_date: str
    verifier_name: str
    confidence_level: float
    notes: str

@dataclass
class ChapterResearchProfile:
    """Research profile for a specific chapter."""
    chapter_number: int
    citations_used: List[str]
    research_elements: List[str]
    verification_checklist: Dict[str, bool]
    technical_accuracy_score: float
    research_gaps: List[str]
    expert_review_status: str

class EnhancedResearchTracker:
    """Enhanced research tracking with automated citation logging and verification."""
    
    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path)
        self.state_dir = self.project_path / ".project-state"
        self.citations_db_path = self.state_dir / "research-citations.json"
        self.verifications_db_path = self.state_dir / "research-verifications.json"
        self.chapter_profiles_path = self.state_dir / "chapter-research-profiles.json"
        
        # Ensure state directory exists
        self.state_dir.mkdir(exist_ok=True)
        
        # Initialize databases
        self.citations_db = self._load_citations_db()
        self.verifications_db = self._load_verifications_db()
        self.chapter_profiles = self._load_chapter_profiles()
    
    def _load_citations_db(self) -> Dict[str, Citation]:
        """Load citations database."""
        if self.citations_db_path.exists():
            try:
                with open(self.citations_db_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {cid: Citation(**citation) for cid, citation in data.items()}
            except (json.JSONDecodeError, TypeError):
                pass
        return {}
    
    def _load_verifications_db(self) -> Dict[str, ResearchVerification]:
        """Load verifications database."""
        if self.verifications_db_path.exists():
            try:
                with open(self.verifications_db_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {vid: ResearchVerification(**verification) 
                           for vid, verification in data.items()}
            except (json.JSONDecodeError, TypeError):
                pass
        return {}
    
    def _load_chapter_profiles(self) -> Dict[str, ChapterResearchProfile]:
        """Load chapter research profiles."""
        if self.chapter_profiles_path.exists():
            try:
                with open(self.chapter_profiles_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {cid: ChapterResearchProfile(**profile) 
                           for cid, profile in data.items()}
            except (json.JSONDecodeError, TypeError):
                pass
        return {}
    
    def save_databases(self):
        """Save all databases to disk."""
        # Save citations
        citations_data = {cid: asdict(citation) for cid, citation in self.citations_db.items()}
        with open(self.citations_db_path, 'w', encoding='utf-8') as f:
            json.dump(citations_data, f, indent=2)
        
        # Save verifications
        verifications_data = {vid: asdict(verification) 
                            for vid, verification in self.verifications_db.items()}
        with open(self.verifications_db_path, 'w', encoding='utf-8') as f:
            json.dump(verifications_data, f, indent=2)
        
        # Save chapter profiles
        profiles_data = {cid: asdict(profile) for cid, profile in self.chapter_profiles.items()}
        with open(self.chapter_profiles_path, 'w', encoding='utf-8') as f:
            json.dump(profiles_data, f, indent=2)
    
    def add_citation(self, citation: Citation) -> str:
        """Add a new citation to the database."""
        citation_id = f"cite_{len(self.citations_db) + 1:03d}"
        citation.id = citation_id
        self.citations_db[citation_id] = citation
        self.save_databases()
        return citation_id
    
    def add_verification(self, verification: ResearchVerification) -> str:
        """Add a new verification to the database."""
        verification_id = f"verify_{len(self.verifications_db) + 1:03d}"
        self.verifications_db[verification_id] = verification
        self.save_databases()
        return verification_id
    
    def analyze_chapter_research(self, chapter_text: str, chapter_number: int) -> ChapterResearchProfile:
        """Analyze a chapter for research elements and generate verification profile."""
        
        # Detect research elements in text
        research_elements = self._detect_research_elements(chapter_text)
        
        # Find citations used
        citations_used = self._extract_citations_from_text(chapter_text)
        
        # Generate verification checklist
        verification_checklist = self._generate_verification_checklist(research_elements)
        
        # Calculate technical accuracy score
        accuracy_score = self._calculate_technical_accuracy(research_elements, citations_used)
        
        # Identify research gaps
        research_gaps = self._identify_research_gaps(research_elements)
        
        # Determine expert review status
        expert_status = self._determine_expert_review_status(research_elements)
        
        profile = ChapterResearchProfile(
            chapter_number=chapter_number,
            citations_used=citations_used,
            research_elements=research_elements,
            verification_checklist=verification_checklist,
            technical_accuracy_score=accuracy_score,
            research_gaps=research_gaps,
            expert_review_status=expert_status
        )
        
        # Store profile
        profile_id = f"chapter_{chapter_number:03d}"
        self.chapter_profiles[profile_id] = profile
        self.save_databases()
        
        return profile
    
    def _detect_research_elements(self, text: str) -> List[str]:
        """Detect research elements that need verification."""
        elements = []
        
        # Technical/Professional terminology patterns
        tech_patterns = [
            r'\b(?:procedure|protocol|regulation|statute|code)\b',
            r'\b(?:investigation|forensic|autopsy|pathology)\b',
            r'\b(?:medication|dosage|diagnosis|treatment|syndrome)\b',
            r'\b(?:warrant|subpoena|jurisdiction|felony|misdemeanor)\b',
            r'\b(?:laboratory|analysis|specimen|evidence|chain of custody)\b'
        ]
        
        for pattern in tech_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            elements.extend([f"technical_term: {match}" for match in matches])
        
        # Professional roles and institutions
        professional_patterns = [
            r'\b(?:detective|officer|sergeant|lieutenant|captain|chief)\b',
            r'\b(?:doctor|nurse|physician|surgeon|pathologist|coroner)\b',
            r'\b(?:lawyer|attorney|prosecutor|judge|clerk)\b',
            r'\b(?:FBI|CIA|DEA|ATF|police department|sheriff|district attorney)\b'
        ]
        
        for pattern in professional_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            elements.extend([f"professional_role: {match}" for match in matches])
        
        # Location-specific elements
        location_patterns = [
            r'\b(?:courthouse|precinct|hospital|morgue|laboratory)\b',
            r'\b(?:downtown|neighborhood|district|county|parish)\b'
        ]
        
        for pattern in location_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            elements.extend([f"location: {match}" for match in matches])
        
        # Remove duplicates and return
        return list(set(elements))
    
    def _extract_citations_from_text(self, text: str) -> List[str]:
        """Extract citation references from chapter text."""
        # Look for citation patterns: [Source: citation_id] or (cite_001)
        citation_patterns = [
            r'\[Source:\s*([^]]+)\]',
            r'\(cite_(\d+)\)',
            r'\[(\d+)\]',  # Numbered citations
            r'According to ([^,]+),',  # Attribution patterns
            r'As ([^,]+) noted,'
        ]
        
        citations = []
        for pattern in citation_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            citations.extend(matches)
        
        return list(set(citations))
    
    def _generate_verification_checklist(self, research_elements: List[str]) -> Dict[str, bool]:
        """Generate verification checklist for research elements."""
        checklist = {}
        
        # Categorize elements and create checklist items
        for element in research_elements:
            if element.startswith('technical_term:'):
                term = element.split(':', 1)[1].strip()
                checklist[f"Verify technical accuracy: {term}"] = False
                checklist[f"Expert review required: {term}"] = False
            
            elif element.startswith('professional_role:'):
                role = element.split(':', 1)[1].strip()
                checklist[f"Verify role responsibilities: {role}"] = False
                checklist[f"Confirm hierarchy accuracy: {role}"] = False
            
            elif element.startswith('location:'):
                location = element.split(':', 1)[1].strip()
                checklist[f"Verify location details: {location}"] = False
                checklist[f"Confirm geographical accuracy: {location}"] = False
        
        # Add general verification items
        if research_elements:
            checklist["Expert consultation completed"] = False
            checklist["Primary sources verified"] = False
            checklist["Cultural sensitivity reviewed"] = False
            checklist["Technical procedures validated"] = False
        
        return checklist
    
    def _calculate_technical_accuracy(self, research_elements: List[str], citations: List[str]) -> float:
        """Calculate technical accuracy score for the chapter."""
        if not research_elements:
            return 10.0  # No technical elements to verify
        
        # Base score
        score = 10.0
        
        # Deduct for missing citations
        citation_ratio = len(citations) / len(research_elements) if research_elements else 1.0
        if citation_ratio < 0.5:
            score -= 3.0
        elif citation_ratio < 0.8:
            score -= 1.5
        
        # Check for verification coverage
        verified_count = 0
        for element in research_elements:
            # Check if this element has corresponding verification
            for verification in self.verifications_db.values():
                if element.lower() in verification.description.lower():
                    if verification.expert_verified:
                        verified_count += 1
                    break
        
        verification_ratio = verified_count / len(research_elements) if research_elements else 1.0
        if verification_ratio < 0.5:
            score -= 4.0
        elif verification_ratio < 0.8:
            score -= 2.0
        
        return max(0.0, score)
    
    def _identify_research_gaps(self, research_elements: List[str]) -> List[str]:
        """Identify gaps in research coverage."""
        gaps = []
        
        # Check for elements without proper verification
        for element in research_elements:
            has_verification = False
            for verification in self.verifications_db.values():
                if element.lower() in verification.description.lower():
                    if verification.expert_verified:
                        has_verification = True
                        break
            
            if not has_verification:
                gaps.append(f"Missing expert verification for: {element}")
        
        # Check for missing citation types
        citation_types = set()
        for citation in self.citations_db.values():
            citation_types.add(citation.type)
        
        required_types = ['expert_interview', 'primary_source', 'field_research']
        for req_type in required_types:
            if req_type not in citation_types and research_elements:
                gaps.append(f"Missing {req_type} citations")
        
        return gaps
    
    def _determine_expert_review_status(self, research_elements: List[str]) -> str:
        """Determine expert review status for the chapter."""
        if not research_elements:
            return "not_required"
        
        # Check for expert verifications
        expert_verified_count = 0
        for element in research_elements:
            for verification in self.verifications_db.values():
                if element.lower() in verification.description.lower():
                    if verification.expert_verified:
                        expert_verified_count += 1
                        break
        
        verification_ratio = expert_verified_count / len(research_elements)
        
        if verification_ratio >= 0.9:
            return "fully_verified"
        elif verification_ratio >= 0.7:
            return "mostly_verified"
        elif verification_ratio >= 0.4:
            return "partially_verified"
        else:
            return "needs_review"
    
    def generate_chapter_verification_checklist(self, chapter_number: int) -> str:
        """Generate verification checklist text for inclusion in chapter."""
        profile_id = f"chapter_{chapter_number:03d}"
        
        if profile_id not in self.chapter_profiles:
            return "<!-- Research verification checklist not available -->"
        
        profile = self.chapter_profiles[profile_id]
        
        checklist_text = f"""
<!-- RESEARCH VERIFICATION CHECKLIST - CHAPTER {chapter_number} -->
<!--
Technical Accuracy Score: {profile.technical_accuracy_score:.1f}/10.0
Expert Review Status: {profile.expert_review_status}
Research Elements Detected: {len(profile.research_elements)}
Citations Used: {len(profile.citations_used)}

VERIFICATION CHECKLIST:
"""
        
        for item, completed in profile.verification_checklist.items():
            status = "✅" if completed else "❌"
            checklist_text += f"{status} {item}\n"
        
        if profile.research_gaps:
            checklist_text += "\nRESEARCH GAPS IDENTIFIED:\n"
            for gap in profile.research_gaps:
                checklist_text += f"⚠️ {gap}\n"
        
        checklist_text += "\nCITATIONS REFERENCED:\n"
        for citation_ref in profile.citations_used:
            checklist_text += f"📖 {citation_ref}\n"
        
        checklist_text += """
Generated by Enhanced Research Tracker
Last Updated: """ + datetime.now().isoformat() + """
-->
"""
        
        return checklist_text
    
    def update_verification_status(self, verification_id: str, verified: bool, verifier: str, notes: str = ""):
        """Update verification status for a research element."""
        if verification_id in self.verifications_db:
            verification = self.verifications_db[verification_id]
            verification.expert_verified = verified
            verification.verifier_name = verifier
            verification.verification_date = datetime.now().isoformat()
            verification.notes = notes
            self.save_databases()
    
    def get_research_summary(self) -> Dict[str, Any]:
        """Get summary of research tracking status."""
        total_citations = len(self.citations_db)
        total_verifications = len(self.verifications_db)
        verified_count = sum(1 for v in self.verifications_db.values() if v.expert_verified)
        
        chapters_with_research = len(self.chapter_profiles)
        total_research_elements = sum(len(p.research_elements) for p in self.chapter_profiles.values())
        
        avg_accuracy = sum(p.technical_accuracy_score for p in self.chapter_profiles.values()) / max(1, chapters_with_research)
        
        return {
            'total_citations': total_citations,
            'total_verifications': total_verifications,
            'verified_elements': verified_count,
            'verification_rate': verified_count / max(1, total_verifications),
            'chapters_tracked': chapters_with_research,
            'total_research_elements': total_research_elements,
            'average_accuracy_score': avg_accuracy,
            'research_gaps_total': sum(len(p.research_gaps) for p in self.chapter_profiles.values())
        }
    
    def export_research_report(self) -> str:
        """Export comprehensive research tracking report."""
        summary = self.get_research_summary()
        
        report = f"""# Research Tracking Report
Generated: {datetime.now().isoformat()}

## Summary Statistics
- Total Citations: {summary['total_citations']}
- Total Verifications: {summary['total_verifications']}
- Verification Rate: {summary['verification_rate']:.1%}
- Chapters Tracked: {summary['chapters_tracked']}
- Average Accuracy Score: {summary['average_accuracy_score']:.1f}/10.0
- Research Gaps: {summary['research_gaps_total']}

## Chapter-by-Chapter Analysis
"""
        
        for chapter_id, profile in sorted(self.chapter_profiles.items()):
            report += f"""
### Chapter {profile.chapter_number}
- Technical Accuracy: {profile.technical_accuracy_score:.1f}/10.0
- Expert Review Status: {profile.expert_review_status}
- Research Elements: {len(profile.research_elements)}
- Citations Used: {len(profile.citations_used)}
- Research Gaps: {len(profile.research_gaps)}

Verification Checklist:
"""
            for item, completed in profile.verification_checklist.items():
                status = "✅" if completed else "❌"
                report += f"  {status} {item}\n"
        
        report += "\n## Citations Database\n"
        for citation_id, citation in self.citations_db.items():
            report += f"""
**{citation_id}:** {citation.title}
- Author: {citation.author}
- Type: {citation.type}
- Reliability: {citation.reliability_score}/10.0
- Status: {citation.verification_status}
"""
        
        return report

# CLI Interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Enhanced Research Tracker")
    parser.add_argument("action", choices=["analyze", "checklist", "summary", "report", "add-citation"], 
                       help="Action to perform")
    parser.add_argument("--chapter-file", help="Chapter file to analyze")
    parser.add_argument("--chapter-number", type=int, help="Chapter number")
    parser.add_argument("--output", help="Output file for report")
    parser.add_argument("--citation-data", help="JSON string with citation data")
    
    args = parser.parse_args()
    
    tracker = EnhancedResearchTracker()
    
    if args.action == "analyze" and args.chapter_file and args.chapter_number:
        try:
            with open(args.chapter_file, 'r', encoding='utf-8') as f:
                chapter_text = f.read()
            
            profile = tracker.analyze_chapter_research(chapter_text, args.chapter_number)
            
            print(f"Research Analysis - Chapter {args.chapter_number}")
            print(f"Technical Accuracy Score: {profile.technical_accuracy_score:.1f}/10.0")
            print(f"Expert Review Status: {profile.expert_review_status}")
            print(f"Research Elements: {len(profile.research_elements)}")
            print(f"Citations Used: {len(profile.citations_used)}")
            print(f"Research Gaps: {len(profile.research_gaps)}")
            
            if profile.research_gaps:
                print("\nResearch Gaps:")
                for gap in profile.research_gaps:
                    print(f"  ⚠️ {gap}")
                    
        except FileNotFoundError:
            print(f"Error: Chapter file not found: {args.chapter_file}")
    
    elif args.action == "checklist" and args.chapter_number:
        checklist = tracker.generate_chapter_verification_checklist(args.chapter_number)
        print(checklist)
    
    elif args.action == "summary":
        summary = tracker.get_research_summary()
        print("Research Tracking Summary:")
        for key, value in summary.items():
            if key == 'verification_rate':
                print(f"  {key.replace('_', ' ').title()}: {value:.1%}")
            elif key == 'average_accuracy_score':
                print(f"  {key.replace('_', ' ').title()}: {value:.1f}/10.0")
            else:
                print(f"  {key.replace('_', ' ').title()}: {value}")
    
    elif args.action == "report":
        report = tracker.export_research_report()
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"Research report saved to {args.output}")
        else:
            print(report)
    
    elif args.action == "add-citation" and args.citation_data:
        try:
            citation_data = json.loads(args.citation_data)
            citation = Citation(**citation_data)
            citation_id = tracker.add_citation(citation)
            print(f"Citation added with ID: {citation_id}")
        except (json.JSONDecodeError, TypeError) as e:
            print(f"Error parsing citation data: {e}")
    
    else:
        print("Please provide required arguments for the specified action")
        parser.print_help() 