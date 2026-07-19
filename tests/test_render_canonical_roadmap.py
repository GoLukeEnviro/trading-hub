import subprocess
from pathlib import Path

RENDER = "orchestrator/scripts/render_canonical_roadmap.py"
OUT = Path("docs/roadmap/canonical-program-roadmap.md")


def _render_to_string():
    return subprocess.run(
        ["python3", RENDER, "--stdout"], capture_output=True, text=True, check=True
    ).stdout


def test_render_is_deterministic():
    assert _render_to_string() == _render_to_string()


def test_render_has_do_not_edit_header():
    assert "GENERATED FROM config/governance/canonical-roadmap.yaml" in _render_to_string()
    assert "DO NOT EDIT MANUALLY" in _render_to_string()


def test_committed_markdown_matches_render():
    assert OUT.read_text() == _render_to_string()
