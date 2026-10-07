"""Standalone release entry: no arguments starts the local web interface."""
import os
import sys
from pathlib import Path

import bootstrap


def main():
    args = [arg for arg in sys.argv[1:] if not arg.startswith('-psn_')]
    if args == ['--plugin-worker']:
        from relay.plugins import worker
        return worker()
    if sys.platform == 'darwin' and not args:
        # Finder has no terminal; retain useful diagnostics outside the bundle.
        for directory in (bootstrap.media_root() / 'logs', Path.home() / 'Library/Logs/AgentRelay'):
            try:
                directory.mkdir(parents=True, exist_ok=True)
                stream = (directory / ('server-%s.log' % os.getpid())).open('a', encoding='utf-8', buffering=1)
                sys.stdout = sys.stderr = stream
                break
            except OSError:
                continue
    import cli
    return cli.main(args or ['serve']) or 0


if __name__ == '__main__':
    raise SystemExit(main())
