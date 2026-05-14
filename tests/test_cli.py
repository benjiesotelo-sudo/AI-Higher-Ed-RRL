from click.testing import CliRunner
from rrl.cli import main

def test_help_lists_commands():
    r = CliRunner().invoke(main, ["--help"])
    assert r.exit_code == 0
    for cmd in ("harvest", "dedup", "enrich", "screen", "export", "all", "status"):
        assert cmd in r.output

def test_each_command_has_help():
    runner = CliRunner()
    for cmd in ("harvest", "dedup", "enrich", "screen", "export", "all", "status"):
        r = runner.invoke(main, [cmd, "--help"])
        assert r.exit_code == 0, f"{cmd} --help failed: {r.output}"

def test_status_runs_without_db(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENALEX_EMAIL", "t@e.com")
    r = CliRunner().invoke(main, ["status"])
    assert r.exit_code in (0, 2)
