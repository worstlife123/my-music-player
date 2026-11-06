#!/usr/bin/env python3
"""Stamp the CI build with a version that the installed player can compare."""

import ast
import os
from pathlib import Path
import re


SOURCE = Path(__file__).resolve().parents[1] / "player_aurora_smart_beautiful_fixed_ui_repaint.py"


def prepare_release(source, run_number, tag=""):
    text = source.read_text(encoding="utf-8")
    assignments = [
        node for node in ast.parse(text).body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "APP_VERSION" for target in node.targets)
    ]
    if len(assignments) != 1:
        raise ValueError("Expected exactly one APP_VERSION assignment")
    node = assignments[0]
    base = ast.literal_eval(node.value)
    if not isinstance(base, str) or not re.fullmatch(r"\d+\.\d+\.\d+(?:\.\d+)?", base):
        raise ValueError("APP_VERSION must contain three or four numeric components")
    if tag:
        if not re.fullmatch(r"v\d+\.\d+\.\d+(?:\.\d+)?", tag):
            raise ValueError("Release tags must have the form v1.2.3 or v1.2.3.4")
        version = tag[1:]
    else:
        if not str(run_number).isdigit() or int(run_number) < 1:
            raise ValueError("A positive GitHub run number is required")
        version = ".".join(base.split(".")[:3] + [str(int(run_number))])
    lines = text.splitlines(keepends=True)
    lines[node.lineno - 1:node.end_lineno] = [f'APP_VERSION = "{version}"\n']
    source.write_text("".join(lines), encoding="utf-8")
    return version


def main():
    tag = os.environ.get("RELEASE_REF_NAME", "") if os.environ.get("RELEASE_REF_TYPE") == "tag" else ""
    version = prepare_release(SOURCE, os.environ.get("RELEASE_RUN_NUMBER", ""), tag)
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        output.write(f"app_version={version}\n")
    print(f"Windows release version: {version}")


if __name__ == "__main__":
    main()
