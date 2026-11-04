"""Native Mac launcher; station data stays outside the app bundle."""
import json
import os
from pathlib import Path
import sys
import traceback


def main():
    defaults = json.loads((Path(sys._MEIPASS) / 'mac-defaults.json').read_text())
    os.environ.setdefault('XRAY_CONFIG', defaults['config'])
    os.environ.setdefault('XRAY_WORKSPACE', defaults['workspace'])
    # Scan subprocesses return JSON through stdout; never redirect that stream.
    if '--acquisition-scan' in sys.argv:
        from acquisition import scan_worker
        scan_worker()
        return
    logs = Path(os.environ['XRAY_WORKSPACE']) / 'state'
    logs.mkdir(parents=True, exist_ok=True)
    with (logs / 'mac-app.log').open('a', encoding='utf-8', buffering=1) as log:
        sys.stdout = sys.stderr = log
        try:
            from launch import main as launch
            launch()
        except Exception:
            traceback.print_exc()
            raise


if __name__ == '__main__':
    main()
