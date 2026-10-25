import os
import signal
import subprocess
import sys

from utils.reporting.terminal import console


def process_options():
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def wait_process(process):
    while True:
        try:
            return process.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            pass


def descendant_pids(pid):
    result = subprocess.run(
        ["ps", "-A", "-o", "pid=,ppid="], capture_output=True, text=True, check=True, timeout=5
    )
    parents = [tuple(map(int, line.split())) for line in result.stdout.splitlines() if line.strip()]
    found = [pid]
    for parent in found:
        found.extend(
            child for child, ancestor in parents if ancestor == parent and child not in found
        )
    return found[1:]


def terminate_tree(process):
    if process.poll() is not None:
        return True
    errors = []
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                timeout=15,
            )
            if result.returncode and process.poll() is None:
                errors.append(f"taskkill: код {result.returncode}")
        else:
            for pid in reversed(descendant_pids(process.pid)):
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        errors.append(str(error))
    if process.poll() is None:
        try:
            process.kill()
        except OSError as error:
            errors.append(str(error))
    try:
        process.wait(timeout=10)
    except (OSError, subprocess.TimeoutExpired) as error:
        errors.append(str(error))
    if errors:
        console.write(
            f"Остановка процесса {process.pid}: " + "; ".join(errors), level="Warn", status="!"
        )
    return process.poll() is not None


def interrupt_and_wait(process):
    if process.poll() is None:
        try:
            process.send_signal(
                signal.CTRL_BREAK_EVENT if sys.platform == "win32" else signal.SIGINT
            )
        except OSError:
            terminate_tree(process)
            return 130
    try:
        process.wait(timeout=30)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        terminate_tree(process)
    return 130
