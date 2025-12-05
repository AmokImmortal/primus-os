"""
subchat_map.py
Links all Subchat components into a single topology map.
Allows the system to understand relationships, dependencies,
and valid transitions between subchat modules.
"""

class SubchatMap:
    def __init__(self):
        # Registry of component → description
        self.components = {}

        # Mapping of dependencies between components
        self.dependencies = {}

        # Mapping of component → allowed transitions
        self.transitions = {}

    def register_component(self, name: str, description: str):
        """Registers a subchat component into the topology map."""
        self.components[name] = description

    def add_dependency(self, component: str, depends_on: list):
        """Stores which components another component requires."""
        self.dependencies[component] = depends_on

    def add_transitions(self, component: str, next_steps: list):
        """Stores allowed transitions from one module to another."""
        self.transitions[component] = next_steps

    def get_component_info(self, name: str):
        """Returns full metadata for a component."""
        return {
            "description": self.components.get(name),
            "dependencies": self.dependencies.get(name, []),
            "transitions": self.transitions.get(name, [])
        }

    def validate_topology(self):
        """Ensures subchat topology is logically consistent."""
        issues = []

        for comp, deps in self.dependencies.items():
            for dep in deps:
                if dep not in self.components:
                    issues.append(f"Missing dependency: {comp} depends on {dep}")

        for comp, next_steps in self.transitions.items():
            for step in next_steps:
                if step not in self.components:
                    issues.append(f"Invalid transition: {comp} → {step}")

        return issues

    def export_map(self):
        """Returns a dictionary snapshot of the entire topology."""
        return {
            "components": self.components,
            "dependencies": self.dependencies,
            "transitions": self.transitions
        }