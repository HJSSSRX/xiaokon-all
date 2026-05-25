"""Hub module — data import/inspection/management tools for the collaboration hub.

Submodules:
    import_yaml  — Import findings/progress from YAML into running Hub
    inspect      — Inspect hub state and findings
    peek_findings — Quick peek at findings
    peek_yaml    — Quick peek at YAML content
    post_clue    — Post a clue/finding to the hub
    role_log     — Role activity logging
"""

from .import_yaml import main as import_yaml_main

__all__ = [
    "import_yaml_main",
]
