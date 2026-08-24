"""Installation of the Linux ``appie://`` protocol handler.

Registers a desktop entry that hands the Albert Heijn login redirect to
``happie auth complete``, so the browser deep link no longer dead-ends in
the address bar on Linux.
"""

import os
import shutil
import subprocess
from pathlib import Path

from happie.auth._flow import AuthenticationError

__all__ = ["DESKTOP_ENTRY_PATH", "ensure_handler"]

#: Fixed location of the desktop entry; no ``XDG_DATA_HOME`` override,
#: consistent with the fixed token path convention.
DESKTOP_ENTRY_PATH = (
    Path.home() / ".local" / "share" / "applications" / "happie.desktop"
)

# The entry is user-readable but not a secret.
_DIR_MODE = 0o755
_FILE_MODE = 0o644


def _desktop_entry_content(cli_path: str) -> str:
    """Render the desktop entry content for ``cli_path``.

    ``%u`` is quoted so URLs containing spaces or ``&`` survive the desktop
    environment's ``Exec`` parsing; the CLI is referenced by absolute path
    because DEs spawn handlers with a restricted ``PATH``.
    """
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=happie\n"
        "NoDisplay=true\n"
        f'Exec="{cli_path}" auth complete %u\n'
        "MimeType=x-scheme-handler/appie;\n"
    )


def _mark_trusted(path: Path) -> None:
    """Mark ``path`` trusted via ``gio``; best effort, failures are ignored.

    GNOME treats desktop entries as untrusted until the mark is set; Plasma
    does not require it, and ``gio`` is absent on minimal systems where it
    does not matter.
    """
    try:
        subprocess.run(
            ["gio", "set", str(path), "trusted", "true"],
            check=False,
            timeout=10,
            capture_output=True,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        pass


def ensure_handler(path: Path = DESKTOP_ENTRY_PATH) -> None:
    """Install or refresh the ``appie://`` scheme-handler desktop entry.

    Resolves the current ``happie`` CLI via ``shutil.which`` and writes the
    desktop entry with an absolute ``Exec`` line. The file is left untouched
    when it already matches; a stale ``Exec`` path (reinstall or update)
    triggers a rewrite, which is the self-heal. On a first write the entry
    is marked trusted via ``gio set`` so GNOME accepts it; the call is best
    effort and its failure is ignored.

    Args:
        path: Where to write the desktop entry; defaults to
            ``~/.local/share/applications/happie.desktop``.

    Raises:
        AuthenticationError: If the ``happie`` CLI cannot be located on the
            ``PATH``.
    """
    cli_path = shutil.which("happie")
    if cli_path is None:
        raise AuthenticationError("Could not locate the happie CLI on the PATH.")

    path = Path(path)
    content = _desktop_entry_content(cli_path)
    existed = path.exists()
    if existed and path.read_text(encoding="utf-8") == content:
        return

    if not existed:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Explicit chmod after creation so a permissive umask cannot weaken
        # the directory mode.
        os.chmod(path.parent, _DIR_MODE)
    path.write_text(content, encoding="utf-8")
    os.chmod(path, _FILE_MODE)
    if not existed:
        _mark_trusted(path)
