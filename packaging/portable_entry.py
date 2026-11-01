"""Entry point for an app-local Windows Python distribution; no global Python install."""
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parent.parent
os.environ['PYTHONUTF8']='1'
os.environ['PYTHONIOENCODING']='utf-8'
os.environ['XRAY_CONFIG'] = str(ROOT/'config/station.json')
os.environ['XRAY_WORKSPACE'] = str(ROOT/'workspace')


def main():
    if '--self-test' in sys.argv:
        from portable_selftest import run
        return run(ROOT)
    print('Opening http://127.0.0.1:8765', flush=True)
    from launch import main as launch
    launch()
    return 0

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        detail=traceback.format_exc()
        print(detail,file=sys.stderr)
        try:
            (ROOT/'logs').mkdir(exist_ok=True)
            with (ROOT/'logs/startup.log').open('a',encoding='utf-8') as file:
                file.write(detail+'\n')
        except OSError:
            pass
        raise SystemExit(1)
