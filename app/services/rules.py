"""Dockerfile audit rules.

Each rule is a function that receives a list of (line_number, line_text) tuples
and returns a list of (level, message) tuples.
"""

from dataclasses import dataclass
from typing import List, Tuple

IssueLevel = str  # "error", "warning", "info"


@dataclass(frozen=True)
class Rule:
    """A single audit rule."""
    name: str
    description: str
    level: str  # "error", "warning", "info"
    check: callable  # (lines: List[Tuple[int, str]]) -> List[Tuple[str, str]]


def _check_no_root_user(lines: List[Tuple[int, str]]) -> List[Tuple[str, str]]:
    """Users should not run as root."""
    results = []
    for i, (num, line) in enumerate(lines):
        if line.strip().startswith("USER") and line.strip().upper().endswith("ROOT"):
            results.append(("warning", f"Line {num}: Running as root is a security risk"))
    return results


def _check_no_add_command(lines: List[Tuple[int, str]]) -> List[Tuple[str, str]]:
    """ADD should be replaced with COPY (ADD auto-extracts tarballs, COPY is explicit)."""
    results = []
    for num, line in lines:
        if line.strip().upper().startswith("ADD ") and not line.strip().upper().startswith("ADD --"):
            results.append(("warning", f"Line {num}: Use COPY instead of ADD"))
    return results


def _check_no_wget_curl(lines: List[Tuple[int, str]]) -> List[Tuple[str, str]]:
    """Avoid downloading files with wget/curl in RUN."""
    results = []
    for num, line in lines:
        stripped = line.strip().upper()
        if ("WGET" in stripped or "CURL" in stripped) and "RUN" in line:
            results.append(("warning", f"Line {num}: Use multi-stage build or COPY instead of wget/curl"))
    return results


def _check_no_rm_cache(lines: List[Tuple[int, str]]) -> List[Tuple[str, str]]:
    """RUN should clean package manager caches."""
    results = []
    for num, line in lines:
        stripped = line.strip()
        if "apt-get install" in stripped and "rm -rf /var/lib/apt/lists/*" not in stripped:
            results.append(("info", f"Line {num}: Consider adding 'rm -rf /var/lib/apt/lists/*' after apt-get install"))
    return results


def _check_single_run(lines: List[Tuple[int, str]]) -> List[Tuple[str, str]]:
    """Multiple RUN instructions can be combined."""
    run_lines = [(i, l) for i, l in lines if l.strip().upper().startswith("RUN")]
    if len(run_lines) > 3:
        results = [(i + 1, l) for i, l in run_lines]
        return [("info", f"Combine {len(results)} RUN instructions into fewer layers")]
    return []


def _check_no_volume(lines: List[Tuple[int, str]]) -> List[Tuple[str, str]]:
    """Review whether volumes should be declared in the image or at runtime."""
    results = []
    for num, line in lines:
        if line.strip().upper().startswith("VOLUME"):
            results.append(("warning", f"Line {num}: VOLUME declares a mount point in the image; review whether runtime mounts are preferable"))
    return results


def _check_no_env_secrets(lines: List[Tuple[int, str]]) -> List[Tuple[str, str]]:
    """Avoid hardcoding secrets in ENV."""
    results = []
    for num, line in lines:
        stripped = line.strip().upper()
        if stripped.startswith("ENV") and any(
            s in stripped for s in ["PASSWORD", "SECRET", "TOKEN", "API_KEY", "PRIVATE_KEY"]
        ):
            results.append(("error", f"Line {num}: Do not hardcode secrets in ENV"))
    return results


def _check_no_latest_tag(lines: List[Tuple[int, str]]) -> List[Tuple[str, str]]:
    """Avoid :latest tag in FROM."""
    results = []
    for num, line in lines:
        if line.strip().upper().startswith("FROM") and ":latest" in line:
            results.append(("warning", f"Line {num}: Pin image tag instead of using :latest"))
    return results


# Registry of all rules
AUDIT_RULES: List[Rule] = [
    Rule(name="no-root-user", description="Users should not run as root", level="warning", check=_check_no_root_user),
    Rule(name="no-add", description="Use COPY instead of ADD", level="warning", check=_check_no_add_command),
    Rule(name="no-wget-curl", description="Avoid wget/curl in RUN", level="warning", check=_check_no_wget_curl),
    Rule(name="rm-cache", description="Clean package manager caches", level="info", check=_check_no_rm_cache),
    Rule(name="single-run", description="Combine RUN instructions", level="info", check=_check_single_run),
    Rule(name="no-volume", description="Review image-declared volumes", level="warning", check=_check_no_volume),
    Rule(name="no-env-secrets", description="Do not hardcode secrets in ENV", level="error", check=_check_no_env_secrets),
    Rule(name="no-latest", description="Pin image tag", level="warning", check=_check_no_latest_tag),
]
