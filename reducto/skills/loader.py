"""
reducto.skills.loader
---------------------
Dynamic loader for autonomous skills.
"""
import importlib.util
import inspect
import logging
import sys
from pathlib import Path
from typing import Dict

from reducto.skills.blueprint import ReductoSkill

logger = logging.getLogger(__name__)

def load_skills_from_directory(skills_dir: Path) -> Dict[str, ReductoSkill]:
    """
    Scans a directory for .py files, safely imports them, and extracts classes
    that inherit from ReductoSkill.
    
    Returns:
        dict: A mapping of skill name to an instantiated ReductoSkill object.
    """
    registry: Dict[str, ReductoSkill] = {}
    
    if not skills_dir.exists() or not skills_dir.is_dir():
        return registry

    for py_file in skills_dir.glob("*.py"):
        if py_file.name == "__init__.py":
            continue
            
        module_name = f"reducto.skills.dynamic.{py_file.stem}"
        
        try:
            # Dynamically load the module
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec is None or spec.loader is None:
                continue
                
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            
            # Execute the module code safely
            spec.loader.exec_module(module)
            
            # Find all ReductoSkill subclasses in the module
            for name, obj in inspect.getmembers(module, inspect.isclass):
                # Ignore the base class itself
                if obj is ReductoSkill:
                    continue
                    
                if issubclass(obj, ReductoSkill):
                    # Instantiate the skill
                    skill_instance = obj()
                    if skill_instance.name:
                        registry[skill_instance.name] = skill_instance
                    else:
                        logger.warning(f"Skill class {obj.__name__} in {py_file.name} has no 'name' defined. Skipping.")
                        
        except Exception as e:
            # Trap the exception so a bad skill doesn't crash the server
            logger.error(f"Failed to load dynamic skill from {py_file.name}: {e}")
            
    return registry
