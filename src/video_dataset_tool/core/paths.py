import os
import shutil
import sys
from pathlib import Path


def canonical_path(path: str | Path) -> str:
    return os.path.normcase(str(Path(path).expanduser().resolve()))


def app_data_dir() -> Path:
    override = os.environ.get("VIDEO_DATASET_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    return base / "VideoDatasetTool"


def find_binary(name: str) -> str | None:
    override = os.environ.get(f"VIDEO_DATASET_{name.upper()}")
    if override:
        return str(Path(override).resolve()) if Path(override).is_file() else None
    found = shutil.which(name)
    if found:
        return found
    # An optional, local installation; no download happens during application startup.
    root = Path(__file__).resolve().parents[3]
    suffix = ".exe" if sys.platform == "win32" else ""
    for candidate in (root / ".tools").glob(f"**/{name}{suffix}"):
        if candidate.is_file():
            return str(candidate)
    return None


def subprocess_options() -> dict:
    import subprocess

    return {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
