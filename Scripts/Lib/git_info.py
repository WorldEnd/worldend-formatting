import subprocess

def curr_git_commit_hash() -> str:
    return subprocess.check_output(['git', 'rev-parse', '--verify', 'HEAD', '--'], text=True).strip()

def is_git_dirty() -> bool:
    status_code = subprocess.run(['git', 'diff-index', '--quiet', 'HEAD', '--']).returncode
    if status_code == 0:
        return False
    elif status_code == 1:
        return True
    else:
        raise AssertionError(f"Status code should be 0 or 1, was {status_code}")

def curr_git_commit_hash_with_dirty() -> str:
    hash = curr_git_commit_hash()
    if is_git_dirty():
        hash += "-dirty"
    return hash