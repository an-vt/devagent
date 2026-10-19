"""Shell routing: POSIX commands need a POSIX shell.

On macOS/Linux ``shell=True`` already means /bin/sh. On Windows it means
cmd.exe, where common POSIX commands do not exist. Use Git Bash when present.
"""

import os
import re
import shutil
import subprocess
from functools import lru_cache

# Drive-letter span: ``C:\\Users\\...`` up to a shell metacharacter.
_DRIVE_PATH_RE = re.compile(r"([A-Za-z]):((?:\\[^\s;&|<>()'\"]+)+)")


def _posixify_drive_paths(command: str) -> str:
    """Rewrite drive-letter paths to Git Bash's ``C:/...`` form."""
    return _DRIVE_PATH_RE.sub(lambda match: match.group(1) + ":" + match.group(2).replace("\\", "/"), command)


@lru_cache(maxsize=1)
def _git_bash() -> str | None:
    """Locate Git Bash on Windows, if installed."""
    if os.name != "nt":
        return None
    candidate = os.path.join(
        os.environ.get("ProgramFiles", r"C:\Program Files"), "Git", "bin", "bash.exe"
    )
    if os.path.isfile(candidate):
        return candidate
    git = shutil.which("git")
    if git:
        derived = os.path.join(os.path.dirname(os.path.dirname(git)), "bin", "bash.exe")
        if os.path.isfile(derived):
            return derived
    return None


def run_shell(command: str, check: bool = False, **kwargs) -> subprocess.CompletedProcess:
    """Run a command via Git Bash on Windows when available."""
    bash = _git_bash()
    if bash is not None:
        return subprocess.run([bash, "-c", _posixify_drive_paths(command)], shell=False, check=check, **kwargs)
    return subprocess.run(command, shell=True, check=check, **kwargs)
