"""Routes for Dockerfile analysis and optimization."""

from fastapi import APIRouter, File, UploadFile, Form
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.services.analyzer import AnalysisResult, analyze_dockerfile, get_instructions
from app.services.generator import OptimizedResult, _generate_dockerignore, generate_optimized_dockerfile

router = APIRouter(prefix="/api", tags=["analysis"])


class DockerfileTextRequest(BaseModel):
    dockerfile_content: str = ""
    include_dockerignore: bool = True


class DockerfileDiffRequest(BaseModel):
    dockerfile_a: str = ""
    dockerfile_b: str = ""

def _analysis_payload(result: AnalysisResult) -> dict:
    return {
        "base_image": result.base_image,
        "base_tag": result.base_tag,
        "uses_latest": result.uses_latest,
        "has_user": result.has_user,
        "has_workdir": result.has_workdir,
        "has_dockerignore": result.has_dockerignore,
        "run_count": result.run_count,
        "copy_count": result.copy_count,
        "add_count": result.add_count,
        "apt_update_without_cleanup": result.apt_update_without_cleanup,
        "copy_dot_dot": result.copy_dot_dot,
        "issues": [
            {
                "level": issue.level.value,
                "message": issue.message,
                "line": issue.line,
            }
            for issue in result.issues
        ],
        "multi_stage_suggestion": result.multi_stage_suggestion,
        "multi_stage_savings_pct": result.multi_stage_savings_pct,
        "multi_stage_changes": result.multi_stage_changes,
        "multi_stage_unified_diff": result.multi_stage_unified_diff,
    }


def _optimization_payload(result: OptimizedResult) -> dict:
    return {
        "original_dockerfile": result.original_dockerfile,
        "optimized_dockerfile": result.optimized_dockerfile,
        "dockerignore": result.dockerignore,
        "original_size": result.original_size,
        "estimated_size": result.estimated_size,
        "changes": result.changes,
    }




async def _read_upload_text(file: UploadFile) -> str:
    return (await file.read()).decode("utf-8")


@router.post("/analyze")
async def analyze_dockerfile_upload(file: UploadFile = File(...)):
    """Analyze an uploaded Dockerfile and return structured report."""
    content = await _read_upload_text(file)
    analysis = analyze_dockerfile(content)
    payload = _analysis_payload(analysis)

    return payload


@router.post("/analyze/text")
async def analyze_dockerfile_text(body: DockerfileTextRequest):
    """Analyze a Dockerfile passed as text."""
    content = body.dockerfile_content
    analysis = analyze_dockerfile(content)
    payload = _analysis_payload(analysis)

    return payload


@router.post("/optimize")
async def optimize_dockerfile(file: UploadFile = File(...), include_dockerignore: bool = Form(True)):
    """Analyze and generate an optimized Dockerfile."""
    content = await _read_upload_text(file)
    analysis = analyze_dockerfile(content)
    optimized = generate_optimized_dockerfile(analysis, content, include_dockerignore)

    optimization_payload = _optimization_payload(optimized)
    return optimization_payload


@router.post("/optimize/text")
async def optimize_dockerfile_text(body: DockerfileTextRequest):
    """Analyze and generate an optimized Dockerfile from text."""
    content = body.dockerfile_content
    include_dockerignore = getattr(body, 'include_dockerignore', True)
    analysis = analyze_dockerfile(content)
    optimized = generate_optimized_dockerfile(analysis, content, include_dockerignore)

    optimization_payload = _optimization_payload(optimized)
    return optimization_payload


@router.post('/diff/text')
async def diff_dockerfiles(body: DockerfileDiffRequest):
    """Produce a lightweight diff between two Dockerfiles (instruction-level and textual unified diff).

    This is a simulation-only diff (does not build images). For image-layer diffs we would need to
    build both images and inspect their layers — that is a heavier operation and requires Docker.
    """
    a = body.dockerfile_a or ""
    b = body.dockerfile_b or ""

    # Analyses
    analysis_a = analyze_dockerfile(a)
    analysis_b = analyze_dockerfile(b)

    # Instruction lists
    instr_a = get_instructions(a)  # list of (start, text)
    instr_b = get_instructions(b)
    instr_a_texts = [t for _, t in instr_a]
    instr_b_texts = [t for _, t in instr_b]

    # Instruction-level diff using SequenceMatcher
    from difflib import SequenceMatcher, unified_diff

    sm = SequenceMatcher(None, instr_a_texts, instr_b_texts)
    instruction_changes = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            for k in range(i1, i2):
                instruction_changes.append({
                    'op': 'equal',
                    'left_index': k,
                    'right_index': k,
                    'left': instr_a_texts[k],
                    'right': instr_b_texts[k],
                })
        elif tag == 'replace':
            length = max(i2 - i1, j2 - j1)
            for idx in range(length):
                left = instr_a_texts[i1 + idx] if i1 + idx < i2 else None
                right = instr_b_texts[j1 + idx] if j1 + idx < j2 else None
                instruction_changes.append({
                    'op': 'replace',
                    'left_index': (i1 + idx) if left is not None else None,
                    'right_index': (j1 + idx) if right is not None else None,
                    'left': left,
                    'right': right,
                })
        elif tag == 'delete':
            for k in range(i1, i2):
                instruction_changes.append({
                    'op': 'delete',
                    'left_index': k,
                    'right_index': None,
                    'left': instr_a_texts[k],
                    'right': None,
                })
        elif tag == 'insert':
            for k in range(j1, j2):
                instruction_changes.append({
                    'op': 'insert',
                    'left_index': None,
                    'right_index': k,
                    'left': None,
                    'right': instr_b_texts[k],
                })

    # Textual unified diff
    a_lines = a.splitlines()
    b_lines = b.splitlines()
    ud = list(unified_diff(a_lines, b_lines, fromfile='A', tofile='B', lineterm=''))

    payload = {
        'analysis_a': _analysis_payload(analysis_a),
        'analysis_b': _analysis_payload(analysis_b),
        'instruction_diff': instruction_changes,
        'textual_diff': ud,
    }

    return payload


@router.get("/dockerignore")
async def download_dockerignore():
    """Download a recommended .dockerignore file."""
    return PlainTextResponse(
        content=_generate_dockerignore(),
        media_type="text/plain",
        headers={"Content-Disposition": "attachment; filename=.dockerignore"},
    )


