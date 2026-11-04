"""Repeat the existing GPU protocol in a new directory, preserving prior reports."""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from experiments.dino import gpu_paired_timing as protocol


def main():
    protocol.OUT = ROOT / 'workspace' / ('dino-gpu-paired-retry-' + time.strftime('%Y%m%d-%H%M%S'))
    protocol.OUT.mkdir(exist_ok=False)
    print('REPORT_DIRECTORY=' + str(protocol.OUT), flush=True)
    protocol.save('protocol.json', dict(order=['base', 'combined', 'combined', 'base', 'combined', 'base', 'base', 'combined'],
        scope='Same photo, ready model/reference, folder wait excluded from primary endpoint; isolated experiment only',
        git_commit=__import__('subprocess').check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()))
    try:
        protocol.main()
    except Exception as exc:
        protocol.save('status.json', dict(status='interrupted', error=str(exc),
            completed_runs=len(protocol.load(protocol.OUT / 'runs.json')) if (protocol.OUT / 'runs.json').exists() else 0))
        raise
    finally:
        print('REPORT_DIRECTORY=' + str(protocol.OUT), flush=True)


if __name__ == '__main__':
    main()
