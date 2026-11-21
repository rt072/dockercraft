"""Dockerfile parser helpers.

Provides logical-line splitting and a lightweight parser that returns instruction
objects (name, args, raw text, start/end line).
"""
from dataclasses import dataclass
from typing import List, Tuple, Optional


InstructionLine = Tuple[int, int, str]  # (start_line, end_line, text)


@dataclass
class ParsedInstruction:
    start: int
    end: int
    name: str
    args: str
    raw: str
    is_json: bool = False


def split_logical_lines(content: str) -> List[InstructionLine]:
    """Split raw Dockerfile content into logical lines, joining continuations.

    Returns list of tuples (start_line, end_line, logical_text).
    """
    logical: List[InstructionLine] = []
    physical_lines = content.splitlines()
    i = 0
    while i < len(physical_lines):
        raw = physical_lines[i]
        start = i + 1
        line = raw.rstrip()
        end = start
        # join continuation lines ending with backslash
        while line.endswith("\\") and i + 1 < len(physical_lines):
            next_raw = physical_lines[i + 1]
            # remove trailing backslash and join with a single space
            line = line[:-1].rstrip() + " " + next_raw.strip()
            i += 1
            end = i + 1
        logical.append((start, end, line.strip()))
        i += 1
    return logical


def parse_dockerfile(content: str) -> List[ParsedInstruction]:
    """Parse Dockerfile into a list of ParsedInstruction (lightweight parser).

    This is not a full Dockerfile grammar parser but handles typical cases:
    - logical line joining (\ continuations)
    - instruction name (first word) and args string
    - JSON-form CMD/ENTRYPOINT detection
    - preserves start/end line numbers
    """
    parsed: List[ParsedInstruction] = []
    for start, end, text in split_logical_lines(content):
        stripped = text.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        parts = stripped.split(maxsplit=1)
        name = parts[0].upper() if parts else ""
        args = parts[1] if len(parts) > 1 else ""
        is_json = args.strip().startswith("[")
        parsed.append(ParsedInstruction(start=start, end=end, name=name, args=args, raw=text, is_json=is_json))
    return parsed
