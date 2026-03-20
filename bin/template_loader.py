#!/usr/bin/env python3
"""Load and match data templates for agent sub-tasks."""
import os, sys, json
from pathlib import Path

JARVIS = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
KNOWLEDGE = JARVIS / "knowledge"

def find_template(domain: str, agent: str) -> dict:
    """Find a data template for the given domain/agent combination."""
    # Search in domain/agent/templates/
    template_dir = KNOWLEDGE / domain / agent / "templates"
    if template_dir.exists():
        for f in template_dir.glob("*.json"):
            try:
                with open(f, encoding="utf-8") as fh:
                    return json.load(fh)
            except Exception:
                continue
    return None

def find_template_by_routing(routing_result: dict) -> dict:
    """Find best template from hierarchical routing result."""
    for centroid in routing_result.get("active_centroids", []):
        domain = centroid["domain"]
        for agent in centroid.get("agents", []):
            template = find_template(domain, agent["name"])
            if template:
                return template
    return None

def format_template_for_prompt(template: dict, user_input: str) -> str:
    """Format template as additional context for the amplified prompt."""
    if not template:
        return ""

    lines = []
    lines.append("DATA TEMPLATE AVAILABLE:")
    lines.append(f"Template: {template.get('template_name', 'Unknown')}")

    # Check which required fields the user might have provided
    input_lower = user_input.lower()
    missing = []
    provided = []
    for field in template.get("required_fields", []):
        # Simple heuristic: check if field name or example appears in input
        name = field["name"].replace("_", " ")
        if name in input_lower or str(field.get("example", "")) in user_input:
            provided.append(field)
        else:
            missing.append(field)

    if missing:
        lines.append("\nThe user has NOT provided these required fields — ask for them or use defaults:")
        for f in missing:
            lines.append(f"  - {f['name']}: {f['description']} (default: {f.get('example', 'N/A')})")

    if provided:
        lines.append(f"\nThe user appears to have provided: {', '.join(f['name'] for f in provided)}")

    # Add equations
    equations = template.get("equations", {})
    if equations:
        lines.append("\nRELEVANT EQUATIONS (use these in your calculations):")
        for name, formula in equations.items():
            if isinstance(formula, dict):
                lines.append(f"  - {name}:")
                for k, v in formula.items():
                    lines.append(f"      {k}: {v}")
            else:
                lines.append(f"  - {name}: {formula}")

    return "\n".join(lines)

if __name__ == "__main__":
    # Quick test
    t = find_template("social_sciences", "finance")
    if t:
        print(f"Found: {t['template_name']}")
        print(format_template_for_prompt(t, "Analyze my portfolio risk at 95% confidence"))
    else:
        print("No template found")
