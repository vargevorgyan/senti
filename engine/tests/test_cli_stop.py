"""`senti stop` must never signal a process that merely reused a stale pid."""
import os
import subprocess
import sys
import types

from senti import cli


def test_stale_pid_of_other_process_is_not_killed(tmp_path, monkeypatch):
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        monkeypatch.setattr(cli, "senti_home", lambda: tmp_path)
        (tmp_path / "senti.pid").write_text(str(other.pid))
        assert cli.cmd_stop(types.SimpleNamespace()) == 0
        assert other.poll() is None, "an unrelated process was killed"
        assert not (tmp_path / "senti.pid").exists()
    finally:
        other.kill()


def test_is_senti_engine_rejects_unrelated_process():
    assert cli._is_senti_engine(os.getpid()) is False
