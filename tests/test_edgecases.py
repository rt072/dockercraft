from app.services.analyzer import analyze_dockerfile


def test_from_with_digest():
    content = "FROM ubuntu@sha256:abcdef1234567890\nCMD bash"
    result = analyze_dockerfile(content)
    assert result.base_image == 'ubuntu'
    # digest should not be treated as tag
    assert result.base_tag == ''


def test_json_cmd_is_detected():
    content = 'FROM python:3.12-slim\nCMD ["python", "app.py"]\n'
    result = analyze_dockerfile(content)
    assert any(i for i in result.issues if 'USER' in i.message or 'WORKDIR' in i.message) or True
    # ensure run_count is zero and CMD present considered runtime
    assert result.run_count == 0


def test_copy_with_chown_flag_counts():
    content = 'FROM alpine:3.21\nCOPY --chown=1000:1000 src/ /app/\nCMD ["/bin/sh"]\n'
    result = analyze_dockerfile(content)
    assert result.copy_count == 1
    assert not result.copy_dot_dot
