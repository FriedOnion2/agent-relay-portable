"""Reject generated Python metadata and test artifacts tracked by Git."""
import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]


def main():
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode('utf-8').split('\0')
    forbidden = []
    for name in filter(None, tracked):
        parts = PurePosixPath(name).parts
        if any(part.endswith('.egg-info') or part in {'.pytest_cache', '.mypy_cache', '.ruff_cache', 'htmlcov'}
               or part == '.coverage' or part.startswith('.coverage.') or part == 'coverage.xml' for part in parts):
            forbidden.append(name)
    if forbidden:
        raise SystemExit('Generated artifacts must not be tracked:\n' + '\n'.join(forbidden))
    print('Repository hygiene passed')


if __name__ == '__main__':
    main()
