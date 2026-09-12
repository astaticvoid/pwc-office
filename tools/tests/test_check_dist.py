"""Tests for check_dist.py security and purity gates."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = TOOLS_DIR.parent
CHECK_DIST = TOOLS_DIR / "check_dist.py"


def run_check_dist(dist_path=None, env_overrides=None):
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    cmd = [sys.executable, str(CHECK_DIST)]
    if dist_path:
        cmd.append(str(dist_path))
    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


def test_check_dist_passes_on_clean_dist():
    # Make sure clean build is present
    res = run_check_dist(env_overrides={"ALLOW_STAGING_AUTH": "0", "ALLOW_STAGING_ORIGIN": "0"})
    assert res.returncode == 0, f"Expected clean dist to pass, got: {res.stdout}\n{res.stderr}"
    assert "dist/ is ready to deploy." in res.stdout


def _setup_mock_dist(tmp_path):
    mock_dist = tmp_path / "mock_dist"
    real_dist = REPO_ROOT / "dist"
    if real_dist.exists():
        shutil.copytree(real_dist, mock_dist)
    else:
        mock_dist.mkdir()
        for f in ("index.html", "app.js", "office.css", "sw.js", "data-provider.js"):
            (mock_dist / f).write_text("/* mock */")
        (mock_dist / "data").mkdir()
        (mock_dist / "data" / "offices.json").write_text("{}")
        (mock_dist / "data" / "collects.json").write_text("{}")
        (mock_dist / "data" / "season_bounds.json").write_text("{}")
    return mock_dist


def test_check_dist_detects_basic_auth_leak(tmp_path):
    mock_dist = _setup_mock_dist(tmp_path)
    data_provider = mock_dist / "data-provider.js"
    data_provider.write_text("const authPlaceholder = 'Basic b2ZmaWNlOmRhaWx5';")

    res = run_check_dist(dist_path=mock_dist, env_overrides={"ALLOW_STAGING_AUTH": "0"})
    assert res.returncode == 1
    assert "data-provider.js contains embedded Basic Auth credentials!" in res.stdout


def test_check_dist_detects_staging_origin_leak(tmp_path):
    mock_dist = _setup_mock_dist(tmp_path)
    data_provider = mock_dist / "data-provider.js"
    data_provider.write_text("const originPlaceholder = 'https://api-staging.praywithoutceasing.ca';")

    res = run_check_dist(dist_path=mock_dist, env_overrides={"ALLOW_STAGING_ORIGIN": "0"})
    assert res.returncode == 1
    assert "data-provider.js contains staging API origin!" in res.stdout


def test_check_dist_detects_secret_files(tmp_path):
    mock_dist = _setup_mock_dist(tmp_path)
    secret_file = mock_dist / ".env.local"
    secret_file.write_text("SECRET=123")

    res = run_check_dist(dist_path=mock_dist)
    assert res.returncode == 1
    assert "secret/credential file detected in dist/: .env.local" in res.stdout
