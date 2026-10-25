import io
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

from tools.runner import processes
from utils.reporting.terminal import Terminal


def test_cancellation_preserves_130_when_forced_wait_fails(monkeypatch):
    process = Mock()
    process.poll.return_value = None
    process.send_signal.side_effect = OSError("console unavailable")
    process.wait.side_effect = subprocess.TimeoutExpired("child", 10)
    monkeypatch.setattr(
        processes.subprocess, "run", Mock(return_value=SimpleNamespace(returncode=0))
    )
    output = io.StringIO()
    monkeypatch.setattr(processes, "console", Terminal(output))
    assert processes.interrupt_and_wait(process) == 130
    process.kill.assert_called_once()
    assert "Остановка процесса" in output.getvalue()


def test_posix_cleanup_visits_descendants_in_separate_sessions(monkeypatch):
    monkeypatch.setattr(processes.sys, "platform", "linux")
    monkeypatch.setattr(processes.signal, "SIGKILL", 9, raising=False)
    monkeypatch.setattr(
        processes.subprocess,
        "run",
        Mock(return_value=SimpleNamespace(stdout="100 1\n200 100\n300 200\n400 1\n")),
    )
    killed = Mock()
    group_killed = Mock()
    monkeypatch.setattr(processes.os, "kill", killed)
    monkeypatch.setattr(processes.os, "killpg", group_killed, raising=False)
    process = Mock(pid=100)
    process.poll.side_effect = [None, 0, 0]
    assert processes.terminate_tree(process)
    assert [call.args[0] for call in killed.call_args_list] == [300, 200]
    group_killed.assert_called_once_with(100, 9)
