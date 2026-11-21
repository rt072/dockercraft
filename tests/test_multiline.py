from app.services.analyzer import analyze_dockerfile
from app.services.generator import generate_optimized_dockerfile
import difflib


def test_multiline_run_and_copy():
    dockerfile = '''FROM python:3.12-slim
COPY . \
    .
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    libssl-dev \
    && echo done
RUN pip install -r requirements.txt
CMD ["python", "app.py"]
'''
    analysis = analyze_dockerfile(dockerfile)
    assert analysis.copy_count == 1
    assert analysis.run_count >= 2

    optimized = generate_optimized_dockerfile(analysis, dockerfile)

    # Optimized should not be identical
    assert optimized.optimized_dockerfile != dockerfile

    # Check that a COPY instruction is present in the optimized output
    assert 'COPY' in optimized.optimized_dockerfile

    # Check apt-get cleanup added
    assert ('apt-get clean' in optimized.optimized_dockerfile) or ('rm -rf /var/lib/apt/lists/*' in optimized.optimized_dockerfile)

    # Print unified diff for review (not used in assertions)
    diff = '\n'.join(difflib.unified_diff(dockerfile.splitlines(), optimized.optimized_dockerfile.splitlines(), lineterm=''))
    print('\n=== DIFF (original -> optimized) ===\n')
    print(diff)
