"""Tests for Dockerfile analyzer."""

from app.services.analyzer import IssueLevel, analyze_dockerfile


def test_analyze_simple_dockerfile():
    """Test basic analysis of a simple Dockerfile."""
    content = """
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD ["python", "app.py"]
"""
    result = analyze_dockerfile(content)
    assert result.base_image == "python"
    assert result.base_tag == "3.12-slim"
    assert not result.uses_latest
    assert result.has_workdir
    assert result.run_count == 1
    assert result.copy_count == 1


def test_analyze_latest_tag():
    """Test detection of 'latest' tag."""
    content = "FROM ubuntu\nRUN apt-get update\nCMD bash"
    result = analyze_dockerfile(content)
    assert result.uses_latest
    assert len(result.issues) >= 1
    assert any(i.level == IssueLevel.WARNING for i in result.issues)


def test_analyze_no_user():
    """Test detection of missing USER instruction."""
    content = "FROM alpine:3.21\nCMD echo hello"
    result = analyze_dockerfile(content)
    assert not result.has_user
    assert any(i.level == IssueLevel.WARNING and "USER" in i.message for i in result.issues)


def test_analyze_run_count():
    """Test RUN count detection."""
    content = "\n".join([f"RUN echo {i}" for i in range(12)]) + "\nCMD bash"
    result = analyze_dockerfile(content)
    assert result.run_count == 12
    assert any("too many" in i.message.lower() for i in result.issues)


def test_analyze_apt_cleanup():
    """Test apt-get cleanup detection."""
    content = "FROM ubuntu\nRUN apt-get update && apt-get install -y curl"
    result = analyze_dockerfile(content)
    assert result.apt_update_without_cleanup
    assert any("cleanup" in i.message.lower() for i in result.issues)


def test_analyze_no_issues():
    """Test a well-formed Dockerfile produces no issues."""
    content = """
FROM python:3.12-slim
RUN apt-get update && apt-get clean && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
USER 1000:1000
CMD ["python", "app.py"]
"""
    result = analyze_dockerfile(content)
    assert not result.uses_latest
    assert result.has_user
    assert result.has_workdir
    assert not result.apt_update_without_cleanup


def test_multi_stage_suggestion_for_build_heavy_dockerfile():
    """Build-heavy Dockerfiles should get a multi-stage suggestion."""
    content = """
FROM node:20
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm install
COPY . .
RUN npm run build
CMD ["node", "server.js"]
"""
    result = analyze_dockerfile(content)

    assert result.multi_stage_suggestion is not None
    assert "AS builder" in result.multi_stage_suggestion
    assert "COPY --from=builder" in result.multi_stage_suggestion
    assert result.multi_stage_savings_pct > 0


def test_no_multi_stage_suggestion_for_simple_runtime_dockerfile():
    """Simple runtime-only Dockerfiles should not get a multi-stage suggestion."""
    content = """
FROM python:3.12-slim
WORKDIR /app
COPY . .
CMD ["python", "app.py"]
"""
    result = analyze_dockerfile(content)

    assert result.multi_stage_suggestion is None
    assert result.multi_stage_changes == []


def test_volume_rule_does_not_claim_volume_is_deprecated():
    """VOLUME should be presented as a runtime-mount recommendation, not deprecated."""
    result = analyze_dockerfile("FROM alpine:3.21\nVOLUME /data\n")
    volume_issues = [issue for issue in result.issues if "VOLUME" in issue.message]

    assert volume_issues
    assert "deprecated" not in volume_issues[0].message.lower()
    assert "mount point" in volume_issues[0].message.lower()
