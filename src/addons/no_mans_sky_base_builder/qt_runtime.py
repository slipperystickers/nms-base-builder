"""Resolve BBE's bundled Qt for widget windows without depending on Blender's wheel directory."""
import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile


# The separate save editor also reads compressed saves through lz4. Its Python
# interpreter does not inherit Blender's managed site-packages.
WHEELS = {
    "lz4-4.4.5-cp313-cp313-win_amd64.whl":
        "da68497f78953017deb20edff0dba95641cc86e7423dfadf7c0264e1ac60dc22",
    "pyside6_essentials-6.11.1-1-cp310-abi3-win_amd64.whl":
        "ce7a97c6fab425c8a345721e2efa063856c14cab5f9b256c02f4b7039833aa8e",
    "shiboken6-6.11.1-cp310-abi3-win_amd64.whl":
        "c2c6863aa80ec18c0f82cea3417837b279cdc60024ac17123461dc9042577df7",
}


def _filesystem_path(path):
    """Use extended paths for the archive contents even with redirected Windows profiles."""
    value = os.path.abspath(path)
    if os.name == "nt" and not value.startswith("\\\\?\\"):
        value = "\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value
    return Path(value)


def bundled_wheels():
    return Path(__file__).resolve().parent / "wheels"


def site(directory):
    directory = Path(directory)
    # The standalone tools also accept an explicit, already extracted Qt installation.
    if (directory / "PySide6" / "__init__.py").is_file():
        return directory
    local = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
    cache = Path(local) / "BaseBuilderExtended" / "qt"
    key = hashlib.sha256("".join(WHEELS.values()).encode("ascii")).hexdigest()[:16]
    target = cache / key
    destination = _filesystem_path(target)
    if not (destination / ".complete").is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".qt-", dir=destination.parent))
        try:
            for filename, expected in WHEELS.items():
                with _filesystem_path(directory / filename).open("rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                        raise ValueError(f"Damaged bundled Qt component: {filename}")
                    stream.seek(0)
                    with zipfile.ZipFile(stream) as archive:
                        archive.extractall(staging)
            (staging / ".complete").touch()
            try:
                staging.rename(destination)
            except OSError:
                # Another BBE process can finish preparing these same verified wheels first.
                if not (destination / ".complete").is_file():
                    raise
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    return destination


def activate(directory=None):
    path = str(site(directory or bundled_wheels()))
    if path not in sys.path:
        sys.path.append(path)
    return path
