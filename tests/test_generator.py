"""Tests for Dockerfile generator."""

from app.services.generator import generate_optimized_dockerfile
from app.services.analyzer import analyze_dockerfile


def test_optimize_simple():
    """Test optimization of a simple Dockerfile."""
    content = "FROM ubuntu\nRUN apt-get update\nCMD bash"
    analysis = analyze_dockerfile(content)
    result = generate_optimized_dockerfile(analysis, content)

    assert result.original_dockerfile == content
    assert result.optimized_dockerfile != content
    assert len(result.changes) > 0
    assert "Pinned" in result.changes[0] or "USER" in str(result.changes)


def test_optimize_combine_runs():
    """Test combining consecutive RUN instructions."""
    content = """FROM python:3.12-slim
RUN pip install flask
RUN pip install gunicorn
RUN pip install redis
CMD ["python", "app.py"]
"""
    analysis = analyze_dockerfile(content)
    result = generate_optimized_dockerfile(analysis, content)

    # Should combine 3 RUNs into one
    assert "Combined" in str(result.changes)
    assert result.optimized_dockerfile.count("RUN") == 1


def test_optimize_apt_cleanup():
    """Test adding apt-get cleanup."""
    content = "FROM ubuntu\nRUN apt-get update && apt-get install -y curl\nCMD bash"
    analysis = analyze_dockerfile(content)
    result = generate_optimized_dockerfile(analysis, content)

    assert "apt-get clean" in result.optimized_dockerfile
    assert "rm -rf /var/lib/apt" in result.optimized_dockerfile


def test_optimize_size_reduction():
    """Test that estimated size is reduced."""
    content = "FROM ubuntu\nRUN apt-get update\nRUN apt-get install -y curl\nCMD bash"
    analysis = analyze_dockerfile(content)
    result = generate_optimized_dockerfile(analysis, content)

    assert result.estimated_size < result.original_size


def test_pip_no_cache_and_combination():
    """Ensure multiple pip installs are combined and --no-cache-dir is used."""
    content = """FROM python:3.12-slim
RUN pip install flask
RUN pip install gunicorn
RUN pip install redis
CMD [\"python\", \"app.py\"]
"""
    analysis = analyze_dockerfile(content)
    result = generate_optimized_dockerfile(analysis, content)

    assert "Combined" in ' '.join(result.changes)
    assert result.optimized_dockerfile.count("RUN") == 1
    assert "--no-cache-dir" in result.optimized_dockerfile


def test_apt_no_install_recommends_added():
    """Ensure apt-get install uses --no-install-recommends when absent."""
    content = "FROM ubuntu\nRUN apt-get update && apt-get install -y curl wget\nCMD bash"
    analysis = analyze_dockerfile(content)
    result = generate_optimized_dockerfile(analysis, content)

    assert "--no-install-recommends" in result.optimized_dockerfile


def test_copy_to_current_directory_is_not_duplicated():
    """Keep ordinary COPY instructions once while rewriting the exact COPY . . form."""
    content = """FROM python:3.13
COPY requirements.txt .
COPY . .
CMD ["python", "app.py"]
"""
    analysis = analyze_dockerfile(content)
    result = generate_optimized_dockerfile(analysis, content)

    assert result.optimized_dockerfile.count("COPY requirements.txt .") == 1
    assert result.optimized_dockerfile.count("COPY . /app") == 1
    assert "COPY . ." not in result.optimized_dockerfile
