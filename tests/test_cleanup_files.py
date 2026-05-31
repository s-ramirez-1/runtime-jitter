# test_cleanup_files.py
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import cleanup_files

# ----------------------------
# FIXTURES
# ----------------------------
@pytest.fixture
def project_dir(tmp_path):
    """
    Creates a fake project structure to test cleanup against
    """
    # files that SHOULD be deleted
    results = tmp_path / "results" / "baseline"
    results.mkdir(parents=True)
    (results / "baseline_001.csv").write_text("run,time_seconds\n0,0.006")
    (results / "baseline_001_meta.json").write_text('{"experiment": "baseline"}')

    plots = tmp_path / "plots" / "baseline"
    plots.mkdir(parents=True)
    (plots / "hist.png").write_bytes(b"fake png data")

    # files that should NOT be deleted
    venv = tmp_path / ".venv" / "lib"
    venv.mkdir(parents=True)
    (venv / "some_config.json").write_text('{"venv": true}')

    git = tmp_path / ".git"
    git.mkdir()
    (git / "config").write_text("git config")

    dashboard = tmp_path / "dashboard"
    dashboard.mkdir()
    (dashboard / "some_asset.png").write_bytes(b"dashboard asset")

    pycache = tmp_path / "__pycache__"
    pycache.mkdir()
    (pycache / "cached.json").write_text("{}")

    return tmp_path


# ----------------------------
# TESTS: FIND TARGETS
# ----------------------------
def test_finds_csv_files(project_dir):
    targets = cleanup_files.find_targets_with_rules(
        project_dir,
        skip_dirs={".venv", ".git", "__pycache__", "dashboard"},
        delete_tex=False
    )
    csv_files = [t for t in targets if t.suffix == ".csv"]
    assert len(csv_files) == 1


def test_finds_json_files(project_dir):
    targets = cleanup_files.find_targets_with_rules(
        project_dir,
        skip_dirs={".venv", ".git", "__pycache__", "dashboard"},
        delete_tex=False
    )
    json_files = [t for t in targets if t.suffix == ".json"]
    assert len(json_files) == 1


def test_finds_png_files(project_dir):
    targets = cleanup_files.find_targets_with_rules(
        project_dir,
        skip_dirs={".venv", ".git", "__pycache__", "dashboard"},
        delete_tex=False
    )
    png_files = [t for t in targets if t.suffix == ".png"]
    assert len(png_files) == 1


# ----------------------------
# TESTS: SKIP DIRS
# ----------------------------
def test_skips_venv(project_dir):
    targets = cleanup_files.find_targets_with_rules(
        project_dir,
        skip_dirs={".venv", ".git", "__pycache__", "dashboard"},
        delete_tex=False
    )
    paths = [str(t) for t in targets]
    assert not any(".venv" in p for p in paths)


def test_skips_git(project_dir):
    targets = cleanup_files.find_targets_with_rules(
        project_dir,
        skip_dirs={".venv", ".git", "__pycache__", "dashboard"},
        delete_tex=False
    )
    paths = [str(t) for t in targets]
    assert not any(".git" in p for p in paths)


def test_skips_dashboard(project_dir):
    targets = cleanup_files.find_targets_with_rules(
        project_dir,
        skip_dirs={".venv", ".git", "__pycache__", "dashboard"},
        delete_tex=False
    )
    paths = [str(t) for t in targets]
    assert not any("dashboard" in p for p in paths)


def test_skips_pycache(project_dir):
    targets = cleanup_files.find_targets_with_rules(
        project_dir,
        skip_dirs={".venv", ".git", "__pycache__", "dashboard"},
        delete_tex=False
    )
    paths = [str(t) for t in targets]
    assert not any("__pycache__" in p for p in paths)


# ----------------------------
# TESTS: TEX HANDLING
# ----------------------------
def test_skips_tex_when_flag_false(project_dir):
    tex_file = project_dir / "results" / "baseline" / "table.tex"
    tex_file.write_text("\\begin{tabular}")

    targets = cleanup_files.find_targets_with_rules(
        project_dir,
        skip_dirs={".venv", ".git", "__pycache__", "dashboard"},
        delete_tex=False
    )
    paths = [str(t) for t in targets]
    assert not any(".tex" in p for p in paths)


def test_includes_tex_when_flag_true(project_dir):
    tex_file = project_dir / "results" / "baseline" / "table.tex"
    tex_file.write_text("\\begin{tabular}")

    targets = cleanup_files.find_targets_with_rules(
        project_dir,
        skip_dirs={".venv", ".git", "__pycache__", "dashboard"},
        delete_tex=True
    )
    paths = [str(t) for t in targets]
    assert any(".tex" in p for p in paths)


# ----------------------------
# TESTS: DELETE FILES
# ----------------------------
def test_delete_files(project_dir, tmp_path):
    test_file = tmp_path / "delete_me.csv"
    test_file.write_text("run,time_seconds\n0,0.006")

    log_file = tmp_path / "deletion_log.txt"
    deleted = cleanup_files.delete_files([test_file], log_file)

    assert not test_file.exists()
    assert len(deleted) == 1


def test_delete_creates_log(project_dir, tmp_path):
    test_file = tmp_path / "delete_me.csv"
    test_file.write_text("run,time_seconds\n0,0.006")

    log_file = tmp_path / "deletion_log.txt"
    cleanup_files.delete_files([test_file], log_file)

    assert log_file.exists()
    log_content = log_file.read_text()
    assert "DELETED" in log_content