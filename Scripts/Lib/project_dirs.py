from pathlib import Path


def root_dir() -> Path:
    if root_dir._found is not None:
        return root_dir._found
    candiate = Path(__file__).resolve().parent.parent.parent
    if (candiate / "Scripts").exists() and (candiate / "Common").exists():
        root_dir._found = candiate.absolute()
        return root_dir._found
    raise AssertionError("Could not find the root dir of the project")


root_dir._found = None


def common_dir() -> Path:
    return root_dir() / "Common"
