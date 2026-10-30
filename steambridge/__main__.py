import argparse
import signal
import sys
import threading

from .mapping import load_profile

def main():
    parser = argparse.ArgumentParser(description='Steam Controller (2026) to virtual Xbox gamepad for Linux')
    parser.add_argument('--headless', action='store_true', help='Run until SIGINT/SIGTERM')
    parser.add_argument('--diagnose', action='store_true', help='Print device and permission information')
    parser.add_argument('--profile', help='JSON profile to load')
    args = parser.parse_args()
    try:
        from . import backend
        if args.diagnose:
            print(backend.diagnostics())
        elif args.headless:
            stop = threading.Event()
            for sig in (signal.SIGTERM, signal.SIGINT):
                signal.signal(sig, lambda *_: stop.set())
            backend.run(stop, load_profile(args.profile), lambda s: print(s, flush=True))
        else:
            from .gui import launch
            launch(args.profile)
        return 0
    except (OSError, ValueError, RuntimeError, ImportError) as exc:
        print(f'SteamBridge: {exc}', file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
