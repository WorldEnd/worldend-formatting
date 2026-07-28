from functools import cache
from pathlib import Path


@cache
def root_dir() -> Path:
    candidate = Path(__file__).resolve().parent.parent.parent
    if (candidate / "Scripts").exists() and (candidate / "Common").exists():
        return candidate.absolute()
    raise AssertionError("Could not find the root dir of the project")


def common_dir() -> Path:
    return root_dir() / "Common"
