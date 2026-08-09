"""Offline validation for committed n8n workflow exports."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SENSITIVE_KEYS = {"password", "secret", "token", "apikey", "api_key", "clientsecret", "client_secret"}
SENSITIVE_VALUE = re.compile(
    r"(?:Bearer\s+[A-Za-z0-9._-]{16,}|sk_(?:live|test)_[A-Za-z0-9]{12,}|-----BEGIN [A-Z ]+PRIVATE KEY-----)"
)


def _scan_for_secrets(value: Any, location: str = "root") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = key.lower().replace("-", "_")
            if normalized in SENSITIVE_KEYS and child not in (None, "", "REPLACE_ME"):
                findings.append(f"{location}.{key}")
            findings.extend(_scan_for_secrets(child, f"{location}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_scan_for_secrets(child, f"{location}[{index}]"))
    elif isinstance(value, str) and SENSITIVE_VALUE.search(value):
        findings.append(location)
    return findings


def validate_workflow(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        workflow = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{path}: invalid JSON: {exc}"]
    if not isinstance(workflow, dict):
        return [f"{path}: root must be an object"]
    nodes = workflow.get("nodes")
    connections = workflow.get("connections")
    if not workflow.get("name") or not isinstance(nodes, list) or not isinstance(connections, dict):
        errors.append(f"{path}: requires name, nodes, and connections")
        return errors
    names = [node.get("name") for node in nodes if isinstance(node, dict)]
    identifiers = [node.get("id") for node in nodes if isinstance(node, dict)]
    if any(not name for name in names) or len(names) != len(set(names)):
        errors.append(f"{path}: node names must be non-empty and unique")
    if any(not identifier for identifier in identifiers) or len(identifiers) != len(set(identifiers)):
        errors.append(f"{path}: node IDs must be non-empty and unique")
    unknown_connection_sources = set(connections) - set(names)
    if unknown_connection_sources:
        errors.append(f"{path}: connections reference unknown nodes {sorted(unknown_connection_sources)}")
    for location in _scan_for_secrets(workflow):
        errors.append(f"{path}: possible embedded secret at {location}")
    return errors


def validate_directory(directory: Path, *, expected_count: int = 8) -> list[Path]:
    paths = sorted(directory.glob("*.json"))
    errors: list[str] = []
    if len(paths) != expected_count:
        errors.append(f"expected {expected_count} workflow JSON files, found {len(paths)}")
    for path in paths:
        errors.extend(validate_workflow(path))
    if errors:
        raise ValueError("\n".join(errors))
    return paths


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", nargs="?", type=Path, default=Path("n8n/workflows"))
    args = parser.parse_args()
    paths = validate_directory(args.directory)
    print(f"Validated {len(paths)} n8n workflow exports; no embedded secret values found.")


if __name__ == "__main__":
    main()
