from __future__ import annotations

from pathlib import Path

from scripts.secret_scan import main, scan_paths


def test_secret_scan_reports_redacted_findings(tmp_path: Path, capsys) -> None:
    secret_file = tmp_path / "config.json"
    secret_file.write_text('{"api_server": {"password": "super-secret-value"}}')

    rc = main(["--root", str(tmp_path), str(secret_file)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "json-sensitive-key" in captured.err
    assert "config.json" in captured.err
    assert "super-secret-value" not in captured.err


def test_secret_scan_allows_env_indirection_and_placeholders(tmp_path: Path) -> None:
    safe_file = tmp_path / "config.example.json"
    safe_file.write_text(
        "{"
        '"api_server": {'
        '"password": "CHANGE_ME_LOCAL_ONLY_PASSWORD", '
        '"jwt_secret_key": "CHANGE_ME_LOCAL_ONLY_SECRET"'
        "}, "
        '"exchange": {'
        '"key": "${BITGET_API_KEY}", '
        '"secret": "${BITGET_API_SECRET}"'
        "}"
        "}"
    )

    findings = scan_paths(tmp_path, [safe_file])

    assert findings == []


def test_secret_scan_detects_known_token_prefix_without_value_leak(tmp_path: Path, capsys) -> None:
    token_file = tmp_path / "token.env"
    fake_token = "ghp_" + ("A" * 36)
    token_file.write_text(f"GITHUB_TOKEN={fake_token}\n")

    rc = main(["--root", str(tmp_path), str(token_file)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "known-token-prefix" in captured.err
    assert fake_token not in captured.err
