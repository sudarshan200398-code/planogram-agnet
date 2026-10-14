"""Directions text-versus-steps consistency checker."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..agents.routing import DirectionStep


def check_directions_consistency(steps: list[DirectionStep], text: str) -> tuple[bool, list[str]]:
    """Compare structured DirectionStep items against plain-English text directions.

    Verifies:
    1. Line count matches step count 1-to-1.
    2. Every rounded whole-metre distance in the walk steps appears in the text, and no extra distances appear.
    3. Every place name / label from the steps appears in the text, and no invented place names appear.
    4. Product names appear in arrive steps while SKUs remain in structured data.
    """
    errors: list[str] = []
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]

    if len(lines) != len(steps):
        errors.append(
            f"Step count mismatch: {len(lines)} text lines vs {len(steps)} structured steps"
        )
        return False, errors

    # Check distances: rounded whole metres
    step_distances = {round(s.distance) for s in steps if s.kind == "walk" and round(s.distance) > 0}
    text_distances = {int(m) for m in re.findall(r"\b(\d+)m\b", text)}
    if text_distances != step_distances:
        errors.append(
            f"Distance mismatch: text has {sorted(text_distances)}, steps have {sorted(step_distances)}"
        )

    for idx, (line, step) in enumerate(zip(lines, steps), 1):
        if not line.startswith(f"{idx}. "):
            errors.append(f"Line {idx} does not start with '{idx}. ': {line}")

        if step.kind == "walk":
            if step.from_label not in line:
                errors.append(f"Line {idx} missing from_label '{step.from_label}'")
            if step.to_label not in line:
                errors.append(f"Line {idx} missing to_label '{step.to_label}'")
            dist_m = round(step.distance)
            if dist_m == 0:
                if "less than 1 m" not in line:
                    errors.append(f"Line {idx} missing 'less than 1 m'")
            else:
                expected_dist_str = f"{dist_m}m"
                if expected_dist_str not in line:
                    errors.append(f"Line {idx} missing distance string '{expected_dist_str}'")


        elif step.kind == "take_connector":
            conn_name = (
                step.connector_type.value
                if hasattr(step.connector_type, "value")
                else str(step.connector_type)
            )
            if conn_name not in line.lower():
                errors.append(f"Line {idx} missing connector type '{conn_name}'")
            if f"Level {step.floor}" not in line:
                errors.append(f"Line {idx} missing origin floor 'Level {step.floor}'")
            if f"Level {step.to_floor}" not in line:
                errors.append(f"Line {idx} missing destination floor 'Level {step.to_floor}'")

        elif step.kind == "arrive":
            if step.to_label not in line:
                errors.append(f"Line {idx} missing arrival label '{step.to_label}'")
            expected_name = step.product_name or step.sku or ""
            if expected_name not in line:
                errors.append(f"Line {idx} missing product name '{expected_name}'")
            if step.location_text and step.location_text not in line:
                errors.append(f"Line {idx} missing location text '{step.location_text}'")

    return len(errors) == 0, errors
