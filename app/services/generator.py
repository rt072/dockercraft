"""Dockerfile generator — produces an optimized version of the input Dockerfile."""

import re
from dataclasses import dataclass, field

from app.services.analyzer import AnalysisResult, split_logical_lines


@dataclass
class OptimizedResult:
    """Result of Dockerfile optimization."""
    original_dockerfile: str = ""
    optimized_dockerfile: str = ""
    dockerignore: str = ""
    original_size: int = 0
    estimated_size: int = 0
    changes: list[str] = field(default_factory=list)


def _pin_base_image(base_image: str, uses_latest: bool) -> str:
    """Suggest a pinned base image if latest is used."""
    if uses_latest and base_image:
        # Common images with recommended pinned versions
        pinned = {
            "python": "python:3.12-slim",
            "node": "node:20-slim",
            "golang": "golang:1.23-alpine",
            "rust": "rust:1.76-slim",
            "ubuntu": "ubuntu:24.04",
            "debian": "debian:bookworm-slim",
            "alpine": "alpine:3.21",
            "nginx": "nginx:1.26-alpine",
            "redis": "redis:7-alpine",
            "postgres": "postgres:17-alpine",
            "mariadb": "mariadb:11.4",
        }
        if base_image in pinned:
            return pinned[base_image]
        return f"{base_image}:latest"
    return base_image


def _generate_dockerignore() -> str:
    """Generate a recommended .dockerignore content."""
    return """# Build artifacts
*.pyc
*.pyo
__pycache__
*.so
*.egg
*.egg-info
dist
build

# Docker
Dockerfile
docker-compose*.yml

# Git
.git
.gitignore

# IDE
.vscode
.idea
*.swp
*.swo

# Docs
*.md
LICENSE

# Environment
.env
.env.*
.venv
venv

# CI/CD
.github
.gitlab-ci.yml

# Logs
*.log
npm-debug.log*
yarn-debug.log*

# OS
.DS_Store
Thumbs.db
"""


def generate_optimized_dockerfile(analysis: AnalysisResult, original_content: str, include_dockerignore: bool = True) -> OptimizedResult:
    """Generate an optimized version of the Dockerfile based on analysis results."""
    changes: list[str] = []
    # Use logical lines (join backslash-continuations) to treat RUN/COPY blocks correctly
    # split_logical_lines returns (start, end, text)
    lines = [text for _, _, text in split_logical_lines(original_content)]
    optimized_lines: list[str] = []

    has_multi_stage = sum(1 for line in lines if line.strip().upper().startswith("FROM")) > 1
    first_stage = True

    # Second pass: generate optimized Dockerfile
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # FROM instruction
        if stripped.upper().startswith("FROM"):
            if first_stage:
                first_stage = False
                # Pin the base image
                if analysis.uses_latest and analysis.base_image:
                    pinned_image = _pin_base_image(analysis.base_image, True)
                    new_from = stripped.replace(f"FROM {analysis.base_image}", f"FROM {pinned_image}")
                    optimized_lines.append(new_from)
                    changes.append(f"Pinned base image: {analysis.base_image} -> {pinned_image}")
                else:
                    optimized_lines.append(stripped)
            else:
                optimized_lines.append(stripped)

        # RUN instruction — combine consecutive RUNs (allow comments/blank lines between)
        elif stripped.upper().startswith("RUN"):
            # Collect RUN parts; allow comments/blank lines between them and preserve comments
            run_parts: list[str] = []
            pre_comments: list[str] = []
            j = i
            # Collect contiguous RUN blocks possibly separated by comments/blanks
            while j < len(lines):
                raw_next = lines[j]
                next_stripped = raw_next.strip()
                if not next_stripped or next_stripped.startswith("#"):
                    # collect comments to preserve before combining
                    pre_comments.append(raw_next)
                    j += 1
                    continue
                if next_stripped.upper().startswith("RUN"):
                    # strip leading RUN
                    cleaned = re.sub(r'^RUN\s+', '', next_stripped, flags=re.IGNORECASE).strip()
                    run_parts.append(cleaned)
                    j += 1
                    continue
                break

            if len(run_parts) > 1:
                # Emit preserved comments that appeared before the first RUN (if any)
                if pre_comments:
                    for c in pre_comments:
                        optimized_lines.append(c)
                # Deduplicate apt-get update and combine
                dedup: list[str] = []
                seen_update = False
                for p in run_parts:
                    lp = p.lower()
                    if 'apt-get update' in lp:
                        if not seen_update:
                            dedup.append(p)
                            seen_update = True
                        else:
                            continue
                    else:
                        dedup.append(p)
                combined = ' && \\\n    '.join(dedup)
                # Apply normalization heuristics to deduped commands (pip/npm/apt flags)
                normalized: list[str] = []
                flags_added = set()
                for p in dedup:
                    np = p
                    # pip -> add --no-cache-dir
                    if re.search(r'(?i)\bpip3?\s+install\b', np) and '--no-cache-dir' not in np:
                        np = re.sub(r'(?i)(\bpip3?\s+install\b)', r'\1 --no-cache-dir', np, count=1)
                        flags_added.add('pip-no-cache')
                    # apt-get install -> add --no-install-recommends
                    if re.search(r'(?i)\bapt(?:-get)?\s+install\b', np) and '--no-install-recommends' not in np:
                        np = re.sub(r'(?i)(\bapt(?:-get)?\s+install\b)', r'\1 --no-install-recommends', np, count=1)
                        flags_added.add('apt-no-install-recommends')
                    # npm install -> add --no-audit --no-fund
                    if re.search(r'(?i)\bnpm\s+install\b', np) and '--no-audit' not in np:
                        np = re.sub(r'(?i)(\bnpm\s+install\b)', r'\1 --no-audit --no-fund', np, count=1)
                        flags_added.add('npm-no-audit')
                    normalized.append(np)

                combined = ' && \
    '.join(normalized)

                # Ensure apt-get cleanup if apt-get used
                if any('apt-get' in p for p in normalized) and 'apt-get clean' not in combined and 'rm -rf /var/lib/apt/lists' not in combined:
                    combined = combined + ' && apt-get clean && rm -rf /var/lib/apt/lists/*'
                    changes.append('Added apt-get clean + rm -rf /var/lib/apt/lists/* when combining RUNs')

                # Record flag changes
                if 'pip-no-cache' in flags_added:
                    changes.append('Use pip --no-cache-dir to avoid caching packages in image')
                if 'apt-no-install-recommends' in flags_added:
                    changes.append('Use apt --no-install-recommends to reduce unnecessary packages')
                if 'npm-no-audit' in flags_added:
                    changes.append('Use npm --no-audit --no-fund to speed up installs and reduce noise')

                optimized_lines.append(f"RUN {combined}")
                changes.append(f"Combined {len(run_parts)} RUN instructions into one")
                i = j - 1

            elif "apt-get update" in stripped and "apt-get clean" not in stripped and "rm -rf /var/lib/apt" not in stripped:
                # Single RUN with apt-get update — add cleanup
                fixed = stripped.rstrip()
                if stripped.endswith("\\"):
                    fixed = stripped[:-2].rstrip() + " \\\n    && apt-get clean && rm -rf /var/lib/apt/lists/*"
                else:
                    fixed = stripped.rstrip() + " && apt-get clean && rm -rf /var/lib/apt/lists/*"
                optimized_lines.append(fixed)
                changes.append("Added apt-get clean + rm -rf /var/lib/apt/lists/* to reduce image size")
            else:
                optimized_lines.append(stripped)

        # COPY instruction
        elif stripped.upper().startswith("COPY"):
            # Rewrite only the exact COPY . . form; preserve every other COPY once.
            if re.fullmatch(r"(?i)COPY\s+\.\s+\.", stripped):
                optimized_lines.append("COPY . /app")
                changes.append("Changed 'COPY . .' to 'COPY . /app' for clarity")
            else:
                optimized_lines.append(stripped)

        # ADD instruction — suggest COPY instead
        elif stripped.upper().startswith("ADD"):
            if ".tar" not in stripped and "http" not in stripped.lower():
                new_add = stripped.replace("ADD ", "COPY ", 1)
                optimized_lines.append(new_add)
                changes.append("Replaced ADD with COPY (use ADD only for archive extraction or URL fetching)")
            else:
                optimized_lines.append(stripped)

        # USER instruction — if missing, add non-root user
        elif stripped.upper().startswith("USER"):
            optimized_lines.append(stripped)

        # WORKDIR instruction
        elif stripped.upper().startswith("WORKDIR"):
            optimized_lines.append(stripped)

        # ENV instruction
        elif stripped.upper().startswith("ENV"):
            optimized_lines.append(stripped)

        # EXPOSE instruction
        elif stripped.upper().startswith("EXPOSE"):
            optimized_lines.append(stripped)

        # CMD / ENTRYPOINT
        elif stripped.upper().startswith(("CMD", "ENTRYPOINT")):
            optimized_lines.append(stripped)

        # Comments
        elif stripped.startswith("#"):
            optimized_lines.append(stripped)

        # Empty lines
        elif not stripped:
            optimized_lines.append("")

        else:
            optimized_lines.append(stripped)

        i += 1

    # If no USER was found, add one before CMD/ENTRYPOINT
    has_user = any(l.strip().upper().startswith("USER") for l in lines)
    if not has_user:
        optimized_lines.append("")
        optimized_lines.append("# Security: run as non-root user")
        optimized_lines.append("USER 1000:1000")
        changes.append("Added non-root USER instruction for security")

    # If no WORKDIR was found, add one
    has_workdir = any(l.strip().upper().startswith("WORKDIR") for l in lines)
    if not has_workdir:
        optimized_lines.append("")
        optimized_lines.append("WORKDIR /app")
        changes.append("Added WORKDIR /app")

    # The Dockerfile input cannot tell us whether a sibling .dockerignore file exists.
    # In particular, comments may mention it without providing the file's contents.
    result_dockerignore = ""
    if include_dockerignore:
        optimized_lines.append("")
        optimized_lines.append("# === Recommended .dockerignore ===")
        dockerignore_content = _generate_dockerignore()
        optimized_lines.append(dockerignore_content)
        changes.append("Added .dockerignore recommendations")
        result_dockerignore = dockerignore_content

    # Multi-stage build suggestion
    if not has_multi_stage and analysis.run_count > 5:
        optimized_lines.append("")
        optimized_lines.append("# === Suggestion: Consider multi-stage build ===")
        optimized_lines.append("# Reduces final image size by separating build dependencies from runtime")
        changes.append("Suggested multi-stage build (many RUN instructions detected)")

    # Estimate size savings
    original_size = len(original_content)
    # Rough heuristic: each combined RUN saves ~5-10% per layer, cleanup saves ~15-20%
    estimated_reduction = 0
    for change in changes:
        if "Combined" in change:
            estimated_reduction += 5
        if "apt-get clean" in change:
            estimated_reduction += 15
        if "Pinned" in change:
            estimated_reduction += 1
        if "COPY" in change and "ADD" in change:
            estimated_reduction += 2
        if "USER" in change:
            estimated_reduction += 1

    estimated_size = int(original_size * (1 - estimated_reduction / 100))

    # Collapse multiple consecutive empty lines to a single blank line for cleaner output
    normalized: list[str] = []
    prev_was_blank = False
    for l in optimized_lines:
        if not l or not l.strip():
            if not prev_was_blank:
                normalized.append("")
                prev_was_blank = True
            else:
                # skip extra blank
                continue
        else:
            normalized.append(l)
            prev_was_blank = False

    optimized_dockerfile = "\n".join(normalized)

    # Post-process: ensure apt/pip/npm flags are present even in single-RUN cases
    try:
        # Add --no-install-recommends to first apt install if not already present anywhere
        if '--no-install-recommends' not in optimized_dockerfile and re.search(r'(?i)\bapt(?:-get)?\s+install\b', optimized_dockerfile):
            optimized_dockerfile = re.sub(r'(?i)(\bapt(?:-get)?\s+install\b)', r'\1 --no-install-recommends', optimized_dockerfile, count=1)
            changes.append('Use apt --no-install-recommends to reduce unnecessary packages')
        # Add pip --no-cache-dir when pip install present
        if '--no-cache-dir' not in optimized_dockerfile and re.search(r'(?i)\bpip3?\s+install\b', optimized_dockerfile):
            optimized_dockerfile = re.sub(r'(?i)(\bpip3?\s+install\b)', r'\1 --no-cache-dir', optimized_dockerfile, count=1)
            changes.append('Use pip --no-cache-dir to avoid caching packages in image')
        # Add npm flags if npm install present
        if '--no-audit' not in optimized_dockerfile and re.search(r'(?i)\bnpm\s+install\b', optimized_dockerfile):
            optimized_dockerfile = re.sub(r'(?i)(\bnpm\s+install\b)', r'\1 --no-audit --no-fund', optimized_dockerfile, count=1)
            changes.append('Use npm --no-audit --no-fund to speed up installs and reduce noise')
    except Exception:
        # best-effort only
        pass

    return OptimizedResult(
        original_dockerfile=original_content,
        optimized_dockerfile=optimized_dockerfile,
        dockerignore=result_dockerignore,
        original_size=original_size,
        estimated_size=estimated_size,
        changes=changes,
    )
