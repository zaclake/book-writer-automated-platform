#!/usr/bin/env python3
"""
Prompt Manager
Loads and manages YAML prompt templates for the 5-stage chapter generation process.
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List
import logging
from dataclasses import dataclass

@dataclass
class PromptTemplate:
    """Represents a loaded prompt template."""
    name: str
    description: str
    stage: int
    goal: str
    system_prompt: str
    user_prompt: str
    quality_gates: List[str]
    variables: Dict[str, List[str]]
    output_format: str
    max_tokens: int
    temperature: float
    metadata: Dict[str, Any]

class PromptManager:
    """Manages prompt templates for chapter generation stages."""
    
    def __init__(self, prompts_dir: str = "prompts"):
        """Initialize the prompt manager."""
        self.prompts_dir = Path(prompts_dir)
        self.templates: Dict[int, PromptTemplate] = {}
        self.logger = logging.getLogger(__name__)
        
        # Load all prompt templates
        self._load_templates()
    
    def _load_templates(self):
        """Load all YAML prompt templates from the prompts directory."""
        if not self.prompts_dir.exists():
            raise FileNotFoundError(f"Prompts directory not found: {self.prompts_dir}")
        
        stage_files = {
            1: "stage_1_strategic_planning.yaml",
            2: "stage_2_first_draft.yaml", 
            3: "stage_3_craft_excellence.yaml",
            4: "stage_4_targeted_refinement.yaml",
            5: "stage_5_final_integration.yaml"
        }
        
        for stage, filename in stage_files.items():
            file_path = self.prompts_dir / filename
            
            if not file_path.exists():
                self.logger.warning(f"Template file not found: {file_path}")
                continue
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    template_data = yaml.safe_load(f)
                
                template = PromptTemplate(
                    name=template_data['name'],
                    description=template_data['description'],
                    stage=template_data['stage'],
                    goal=template_data['goal'],
                    system_prompt=template_data['system_prompt'],
                    user_prompt=template_data['user_prompt'],
                    quality_gates=template_data.get('quality_gates', []),
                    variables=template_data.get('variables', {}),
                    output_format=template_data.get('output_format', 'text'),
                    max_tokens=template_data.get('max_tokens', 4000),
                    temperature=template_data.get('temperature', 0.7),
                    metadata=template_data
                )
                
                self.templates[stage] = template
                self.logger.info(f"Loaded template for stage {stage}: {template.name}")
                
            except Exception as e:
                self.logger.error(f"Failed to load template {file_path}: {e}")
    
    def get_template(self, stage: int) -> Optional[PromptTemplate]:
        """Get the template for a specific stage."""
        return self.templates.get(stage)
    
    def get_all_templates(self) -> Dict[int, PromptTemplate]:
        """Get all loaded templates."""
        return self.templates.copy()
    
    def validate_variables(self, stage: int, variables: Dict[str, Any]) -> tuple[bool, List[str]]:
        """Validate that all required variables are provided for a stage."""
        template = self.get_template(stage)
        if not template:
            return False, [f"Template not found for stage {stage}"]
        
        errors = []
        required_vars = template.variables.get('required', [])
        
        for var in required_vars:
            if var not in variables:
                errors.append(f"Required variable missing: {var}")
            elif variables[var] is None:
                errors.append(f"Required variable is None: {var}")
        
        return len(errors) == 0, errors
    
    def render_prompts(self, stage: int, variables: Dict[str, Any]) -> tuple[str, str]:
        """Render system and user prompts with provided variables."""
        template = self.get_template(stage)
        if not template:
            raise ValueError(f"Template not found for stage {stage}")
        
        # Validate variables
        is_valid, errors = self.validate_variables(stage, variables)
        if not is_valid:
            raise ValueError(f"Variable validation failed: {errors}")
        
        # Replace None values with empty strings for optional variables
        safe_variables = {}
        for key, value in variables.items():
            safe_variables[key] = value if value is not None else ""
        
        try:
            system_prompt = template.system_prompt.format(**safe_variables)
            user_prompt = template.user_prompt.format(**safe_variables)
            return system_prompt, user_prompt
        except KeyError as e:
            raise ValueError(f"Template variable not provided: {e}")
    
    def get_stage_config(self, stage: int) -> Dict[str, Any]:
        """Get configuration parameters for a stage."""
        template = self.get_template(stage)
        if not template:
            return {}
        
        return {
            'max_tokens': template.max_tokens,
            'temperature': template.temperature,
            'output_format': template.output_format,
            'quality_gates': template.quality_gates
        }
    
    def list_available_stages(self) -> List[int]:
        """List all available stage numbers."""
        return sorted(self.templates.keys())
    
    def get_stage_info(self, stage: int) -> Dict[str, Any]:
        """Get information about a specific stage."""
        template = self.get_template(stage)
        if not template:
            return {}
        
        return {
            'stage': template.stage,
            'name': template.name,
            'description': template.description,
            'goal': template.goal,
            'required_variables': template.variables.get('required', []),
            'optional_variables': template.variables.get('optional', []),
            'quality_gates': template.quality_gates
        }
    
    def create_variable_template(self, stage: int) -> Dict[str, Any]:
        """Create a template dictionary with all variables for a stage."""
        template = self.get_template(stage)
        if not template:
            return {}
        
        variable_template = {}
        
        # Add required variables
        for var in template.variables.get('required', []):
            variable_template[var] = f"<{var}>"
        
        # Add optional variables
        for var in template.variables.get('optional', []):
            variable_template[var] = f"<{var}_optional>"
        
        return variable_template

def main():
    """Test the prompt manager."""
    manager = PromptManager()
    
    print("Available stages:")
    for stage in manager.list_available_stages():
        info = manager.get_stage_info(stage)
        print(f"  Stage {stage}: {info['name']}")
        print(f"    Description: {info['description']}")
        print(f"    Required variables: {info['required_variables']}")
        print(f"    Optional variables: {info['optional_variables']}")
        print()
    
    # Test variable template creation
    print("Variable template for Stage 1:")
    template_vars = manager.create_variable_template(1)
    for var, placeholder in template_vars.items():
        print(f"  {var}: {placeholder}")

if __name__ == "__main__":
    main() 