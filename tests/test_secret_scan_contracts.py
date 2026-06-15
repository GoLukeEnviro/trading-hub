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


# ── Assignment-pattern detection (env-style key=value in non-JSON files) ──


def test_assign_detects_api_key_in_env_file(tmp_path: Path, capsys) -> None:
    env_file = tmp_path / "secrets.env"
    env_file.write_text("API_KEY=sk-live-abcdef1234567890abcdef12\n")

    rc = main(["--root", str(tmp_path), str(env_file)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "assignment-pattern" in captured.err
    assert "sk-live" not in captured.err


def test_assign_detects_password_in_sh_file(tmp_path: Path, capsys) -> None:
    sh_file = tmp_path / "deploy.sh"
    sh_file.write_text('export PASSWORD="supersecret!2026"\n')

    rc = main(["--root", str(tmp_path), str(sh_file)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "assignment-pattern" in captured.err
    assert "supersecret" not in captured.err


def test_assign_detects_token_in_yaml_file(tmp_path: Path, capsys) -> None:
    yaml_file = tmp_path / "config.yml"
    yaml_file.write_text("token: '123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11'\n")

    rc = main(["--root", str(tmp_path), str(yaml_file)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "assignment-pattern" in captured.err
    assert "ABC-DEF" not in captured.err


def test_assign_ignores_env_var_indirection(tmp_path: Path) -> None:
    safe_file = tmp_path / "config.sh"
    safe_file.write_text(
        'export API_KEY="${BITGET_API_KEY}"\n'
        'export SECRET="${BITGET_API_SECRET}"\n'
    )

    findings = scan_paths(tmp_path, [safe_file])
    assert findings == []


def test_assign_ignores_known_placeholders(tmp_path: Path) -> None:
    safe_file = tmp_path / "config.sh"
    safe_file.write_text(
        'export API_KEY="CHANGE_ME"\n'
        'export SECRET="YOUR_SECRET_HERE"\n'
        'export PASSWORD="PLACEHOLDER"\n'
    )

    findings = scan_paths(tmp_path, [safe_file])
    assert findings == []


def test_assign_ignores_short_values(tmp_path: Path) -> None:
    safe_file = tmp_path / "config.sh"
    safe_file.write_text('export MODE="enabled"\n')

    findings = scan_paths(tmp_path, [safe_file])
    assert findings == []
