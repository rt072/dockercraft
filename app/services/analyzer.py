"""Dockerfile analyzer — checks best practices and returns structured report."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from app.services.rules import AUDIT_RULES

DOCKERFILE_INSTRUCTIONS = {
    "RUN",
    "COPY",
    "ADD",
    "FROM",
    "USER",
    "VOLUME",
    "WORKDIR",
    "ENV",
    "ARG",
    "EXPOSE",
    "CMD",
    "ENTRYPOINT",
    "SHELL",
    "HEALTHCHECK",
    "ONBUILD",
    "STOPSIGNAL",
    "MAINTAINER",
}

BUILD_TOOL_HINTS = (
    "apt-get install",
    "apk add",
    "yum install",
    "dnf install",
    "pip install",
    "poetry install",
    "npm install",
    "yarn install",
    "pnpm install",
    "go build",
    "cargo build",
    "rustc",
    "dotnet publish",
    "mvn package",
    "gradle build",
    "make",
    "cmake",
    "gcc",
    "g++",
)

BUILD_OUTPUT_HINTS = (
    "npm run build",
    "yarn build",
    "pnpm build",
    "go build",
    "cargo build",
    "dotnet publish",
    "mvn package",
    "gradle build",
    "make",
)


class IssueLevel(str, Enum):
    WARNING = "warning"
    INFO = "info"
    ERROR = "error"


@dataclass
class Issue:
    level: IssueLevel
    message: str
    line: Optional[int] = None


@dataclass
class AnalysisResult:
    base_image: str = ""
    base_tag: str = ""
    uses_latest: bool = False
    has_user: bool = False
    has_workdir: bool = False
    has_dockerignore: bool = False
    run_count: int = 0
    copy_count: int = 0
    add_count: int = 0
    apt_update_without_cleanup: bool = False
    copy_dot_dot: bool = False
    issues: list[Issue] = field(default_factory=list)
    multi_stage_suggestion: Optional[str] = None
    multi_stage_savings_pct: float = 0.0
    multi_stage_changes: list[str] = field(default_factory=list)
    multi_stage_unified_diff: list[str] = field(default_factory=list)


Instruction = tuple[int, str]


def split_logical_lines(content: str) -> list[Instruction]:
    """Split raw Dockerfile content into logical lines, joining lines continued with backslashes.

    Returns list of (start_line_number, logical_line_text).
    """
    logical: list[Instruction] = []
    physical_lines = content.splitlines()
    i = 0
    while i < len(physical_lines):
        raw = physical_lines[i]
        start = i + 1
        line = raw.rstrip()
        # join continuation lines ending with backslash
        while line.endswith("\\") and i + 1 < len(physical_lines):
            next_raw = physical_lines[i + 1]
            # remove trailing backslash and join with a single space
            line = line[:-1].rstrip() + " " + next_raw.strip()
            i += 1
        logical.append((start, line.strip()))
        i += 1
    return logical


# Prefer production parser (dockerfile-parse) if available, otherwise use our lightweight parser
try:
    from dockerfile_parse import DockerfileParser as DockerfileParser
except Exception:
    DockerfileParser = None

from app.services.parser import parse_dockerfile, split_logical_lines


def _collect_instructions(content: str) -> list[Instruction]:
    """Collect Dockerfile instructions using a production parser if available,
    otherwise fall back to our lightweight parser.

    Returns list of (start_line_number, instruction_text).
    """
    instructions: list[Instruction] = []

    # 1) If dockerfile-parse is installed, try to use its structure
    if DockerfileParser is not None:
        try:
            dfp = DockerfileParser()
            dfp.content = content
            # dfp.structure is a list of dicts; map entries to instruction tuples
            for entry in getattr(dfp, 'structure', []) or []:
                instr = entry.get('instruction') or entry.get('instruction') or ''
                instr_name = instr.upper() if instr else ''
                if instr_name in DOCKERFILE_INSTRUCTIONS:
                    start = entry.get('startline') if entry.get('startline') is not None else entry.get('start', 1)
                    # content key may exist
                    text = entry.get('content') or entry.get('value') or ''
                    if not text:
                        # fallback to reconstruct
                        text = instr_name + (' ' + (entry.get('value') or ''))
                    instructions.append((start, text.strip()))
            if instructions:
                return instructions
        except Exception:
            # if external parser fails, fallback to our parser
            pass

    # 2) Try our internal parse_dockerfile (lightweight parser)
    try:
        parsed = parse_dockerfile(content)
        for instr in parsed:
            if instr.name and instr.name.upper() in DOCKERFILE_INSTRUCTIONS:
                text = instr.name + (" " + instr.args if instr.args else "")
                instructions.append((instr.start, text.strip()))
        if instructions:
            return instructions
    except Exception:
        pass

    # 3) Fallback: simple logical-line splitting
    for line_number, line in split_logical_lines(content):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        keyword = stripped.split(maxsplit=1)[0].upper()
        if keyword in DOCKERFILE_INSTRUCTIONS:
            instructions.append((line_number, stripped))
    return instructions


def _extract_base_image(from_instruction: str) -> tuple[str, str]:
    parts = from_instruction.split()
    if len(parts) < 2:
        return "", ""

    image_ref = parts[1]
    # Handle digest syntax (image@sha256:...) — extract name before @
    if '@' in image_ref:
        name_with_registry = image_ref.split('@', 1)[0]
        base_tag = ""
    else:
        # Determine tag vs registry port: tag is present if last ':' is after last '/'
        last_slash = image_ref.rfind('/')
        last_colon = image_ref.rfind(':')
        if last_colon > last_slash:
            base_tag = image_ref[last_colon + 1:]
            name_with_registry = image_ref[:last_colon]
        else:
            base_tag = ""
            name_with_registry = image_ref
    # Short image name (without registry) for mapping (e.g., 'python', 'node')
    base_image_short = name_with_registry.split('/')[-1].lower()
    return base_image_short, base_tag


def _has_runtime_command(instructions: list[Instruction]) -> bool:
    return any(text.upper().startswith(("CMD", "ENTRYPOINT")) for _, text in instructions)


def _infer_workdir(instructions: list[Instruction]) -> str:
    for _, text in instructions:
        if text.upper().startswith("WORKDIR"):
            parts = text.split(maxsplit=1)
            if len(parts) == 2:
                return parts[1]
    return "/app"


def _infer_artifact_copy(workdir: str, run_commands: list[str]) -> tuple[str, str]:
    if any("npm run build" in cmd or "yarn build" in cmd or "pnpm build" in cmd for cmd in run_commands):
        return f"COPY --from=builder {workdir}/dist {workdir}/dist", "frontend build artifacts"
    if any("go build" in cmd for cmd in run_commands):
        return f"COPY --from=builder {workdir}/app /usr/local/bin/app", "compiled Go binary"
    if any("cargo build" in cmd for cmd in run_commands):
        return f"COPY --from=builder {workdir}/target/release/app /usr/local/bin/app", "compiled Rust binary"
    if any("dotnet publish" in cmd for cmd in run_commands):
        return f"COPY --from=builder {workdir}/out {workdir}", ".NET publish output"
    if any("mvn package" in cmd or "gradle build" in cmd for cmd in run_commands):
        return f"COPY --from=builder {workdir}/target {workdir}/target", "Java build output"
    return f"COPY --from=builder {workdir} {workdir}", "runtime artifacts only"


def _estimate_multi_stage_savings(run_commands: list[str], run_count: int) -> float:
    savings = 25.0

    if any(
        hint in cmd
        for cmd in run_commands
        for hint in ("npm run build", "go build", "cargo build", "dotnet publish", "mvn package", "gradle build")
    ):
        savings += 20.0

    if any(hint in cmd for cmd in run_commands for hint in ("apt-get install", "apk add", "yum install", "dnf install")):
        savings += 10.0

    if run_count >= 4:
        savings += 5.0

    return min(savings, 65.0)


def suggest_multi_stage(instructions: list[Instruction]) -> tuple[Optional[str], float, list[str]]:
    """Build a multi-stage suggestion when the Dockerfile looks build-heavy."""
    from_lines = [text for _, text in instructions if text.upper().startswith("FROM")]
    if len(from_lines) != 1:
        return None, 0.0, []

    run_commands = [text[4:].strip().lower() for _, text in instructions if text.upper().startswith("RUN ")]
    if not run_commands or not _has_runtime_command(instructions):
        return None, 0.0, []

    uses_build_tools = any(hint in cmd for cmd in run_commands for hint in BUILD_TOOL_HINTS)
    produces_build_output = any(hint in cmd for cmd in run_commands for hint in BUILD_OUTPUT_HINTS)
    copies_project = any(text.upper().startswith(("COPY", "ADD")) for _, text in instructions)

    if not uses_build_tools or not (produces_build_output or copies_project):
        return None, 0.0, []
    if not produces_build_output and len(run_commands) < 2:
        return None, 0.0, []

    image_ref = from_lines[0].split()[1]
    workdir = _infer_workdir(instructions)
    artifact_copy, artifact_note = _infer_artifact_copy(workdir, run_commands)
    runtime_command = next(
        (text for _, text in reversed(instructions) if text.upper().startswith(("CMD", "ENTRYPOINT"))),
        None,
    )
    if not runtime_command:
        return None, 0.0, []

    build_stage_lines = [f"FROM {image_ref} AS builder"]
    if all(not text.upper().startswith("WORKDIR") for _, text in instructions):
        build_stage_lines.append(f"WORKDIR {workdir}")

    for _, text in instructions:
        prefix = text.split(maxsplit=1)[0].upper()
        if prefix in {"FROM", "CMD", "ENTRYPOINT", "EXPOSE", "HEALTHCHECK", "USER"}:
            continue
        build_stage_lines.append(text)

    runtime_stage_lines = ["", f"FROM {image_ref}"]
    runtime_metadata: list[str] = []
    for _, text in instructions:
        prefix = text.split(maxsplit=1)[0].upper()
        if prefix in {"WORKDIR", "ENV", "ARG", "EXPOSE", "USER", "HEALTHCHECK"}:
            if text not in runtime_metadata:
                runtime_metadata.append(text)

    if all(not text.upper().startswith("WORKDIR") for text in runtime_metadata):
        runtime_stage_lines.append(f"WORKDIR {workdir}")
    runtime_stage_lines.extend(runtime_metadata)
    runtime_stage_lines.append("# Adjust the artifact path below if your build output uses a different directory")
    runtime_stage_lines.append(artifact_copy)
    runtime_stage_lines.append(runtime_command)

    suggestion = "\n".join(build_stage_lines + runtime_stage_lines)
    savings = _estimate_multi_stage_savings(run_commands, len(run_commands))
    changes = [
        "Split build dependencies into a dedicated builder stage",
        f"Copy only {artifact_note} into the final image",
        f"Estimated image size reduction: ~{savings:.0f}%",
    ]
    return suggestion, savings, changes


def get_instructions(content: str) -> list[Instruction]:
    """Return collected Dockerfile instructions (start_line, text).

    This is a thin wrapper around the internal _collect_instructions so routes
    and other services can reuse a stable helper for instruction-level diffs.
    """
    return _collect_instructions(content)


def analyze_dockerfile(content: str) -> AnalysisResult:
    """Analyze a Dockerfile content and return a structured report."""
    result = AnalysisResult()
    instructions = _collect_instructions(content)

    from_lines = [item for item in instructions if item[1].upper().startswith("FROM")]
    if from_lines:
        line_number, first_from = from_lines[0]
        result.base_image, result.base_tag = _extract_base_image(first_from)
        image_ref = first_from.split()[1] if len(first_from.split()) >= 2 else ""
        if not result.base_tag:
            result.uses_latest = True
            result.issues.append(Issue(
                level=IssueLevel.WARNING,
                message=f"Base image '{image_ref}' has no tag (defaults to 'latest'). Pin an exact version.",
                line=line_number,
            ))
        elif result.base_tag == "latest":
            result.uses_latest = True
            result.issues.append(Issue(
                level=IssueLevel.WARNING,
                message=f"Base image '{image_ref}' uses 'latest' tag. Pin an exact version for reproducibility.",
                line=line_number,
            ))

    user_lines = [item for item in instructions if item[1].upper().startswith("USER")]
    result.has_user = bool(user_lines)
    if not result.has_user:
        result.issues.append(Issue(
            level=IssueLevel.WARNING,
            message="No 'USER' instruction found. Consider running as a non-root user for security.",
        ))

    workdir_lines = [item for item in instructions if item[1].upper().startswith("WORKDIR")]
    result.has_workdir = bool(workdir_lines)
    if not result.has_workdir:
        result.issues.append(Issue(
            level=IssueLevel.INFO,
            message="No 'WORKDIR' instruction found. Consider setting a working directory.",
        ))

    run_lines = [item for item in instructions if item[1].upper().startswith("RUN")]
    result.run_count = len(run_lines)
    if result.run_count > 10:
        result.issues.append(Issue(
            level=IssueLevel.WARNING,
            message=f"Too many RUN instructions ({result.run_count}). Consider combining them to reduce layers.",
        ))

    copy_lines = [item for item in instructions if item[1].upper().startswith("COPY")]
    result.copy_count = len(copy_lines)
    for line_number, line in copy_lines:
        parts = line.split()[1:]
        if len(parts) >= 2 and parts[-1] == ".":
            result.copy_dot_dot = True
            result.issues.append(Issue(
                level=IssueLevel.WARNING,
                message="Using 'COPY . .' copies the entire build context. Use specific paths or a .dockerignore.",
                line=line_number,
            ))

    add_lines = [item for item in instructions if item[1].upper().startswith("ADD")]
    result.add_count = len(add_lines)
    if result.add_count:
        result.issues.append(Issue(
            level=IssueLevel.INFO,
            message="ADD is used. Prefer COPY unless you need auto-extraction of archives or URL fetching.",
        ))

    for line_number, line in run_lines:
        lowered = line.lower()
        if "apt-get update" in lowered and "apt-get clean" not in lowered and "rm -rf /var/lib/apt" not in lowered:
            result.apt_update_without_cleanup = True
            result.issues.append(Issue(
                level=IssueLevel.WARNING,
                message="apt-get update without cleanup (apt-get clean / rm -rf /var/lib/apt). This increases image size.",
                line=line_number,
            ))

    for rule in AUDIT_RULES:
        for level, message in rule.check(instructions):
            result.issues.append(Issue(level=IssueLevel(level), message=message))

    suggestion, savings, changes = suggest_multi_stage(instructions)
    if suggestion:
        result.multi_stage_suggestion = suggestion
        result.multi_stage_savings_pct = savings
        result.multi_stage_changes = changes
        # Compute unified textual diff between original content and suggestion for preview/patch
        try:
            from difflib import unified_diff
            orig_lines = content.splitlines()
            sugg_lines = suggestion.splitlines()
            ud = list(unified_diff(orig_lines, sugg_lines, fromfile='original', tofile='multi-stage-suggestion', lineterm=''))
            result.multi_stage_unified_diff = ud
        except Exception:
            result.multi_stage_unified_diff = []

    return result
