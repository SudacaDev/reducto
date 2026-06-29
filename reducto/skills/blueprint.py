"""
reducto.skills.blueprint
------------------------
Contratos y clases base para las Autonomous Skills de Reducto.
"""

from typing import Any

class ReductoSkill:
    """
    Clase base estricta para todas las Autonomous Skills generadas por LLMs.
    
    Toda skill DEBE heredar de esta clase e implementar el método execute().
    """
    
    # Nombre identificador de la skill (ej: "detect_god_classes")
    name: str = ""
    
    # Descripción de lo que hace la skill (para el MCP)
    description: str = ""
    
    # JSON Schema de los inputs que acepta la skill (para el MCP)
    input_schema: dict = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    def execute(self, graph: Any, arguments: dict[str, Any]) -> dict[str, Any] | str:
        """
        Ejecuta la lógica de la skill.
        
        Args:
            graph: Una instancia de reducto.graph.core.ReductoGraph.
            arguments: Los argumentos validados según input_schema.
            
        Returns:
            Un diccionario o string que será devuelto al LLM a través de MCP.
        """
        raise NotImplementedError("Skill must implement execute()")
