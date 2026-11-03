"""Windows portable entry: writable state stays next to the executable."""
import json
import os
from pathlib import Path
import sys
import traceback


def main():
    root = Path(sys.executable).resolve().parent
    os.chdir(root)
    # A copied package must never inherit the developer workstation's locations.
    os.environ['XRAY_CONFIG'] = str(root / 'config/station.json')
    os.environ['XRAY_WORKSPACE'] = str(root / 'workspace')
    os.environ['PYTHONUTF8'] = '1'
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    if '--self-test' in sys.argv:
        from portable_release_check import run
        return run(root)
    if '--acquisition-scan' in sys.argv:
        from acquisition import scan_worker
        scan_worker()
        return 0
    # Rebase only reference images actually stored inside this portable workspace.
    # The application writes absolute paths after uploads; moving the folder is safe.
    settings_path = root / 'workspace/state/ui_settings.json'
    if settings_path.exists():
        settings = json.loads(settings_path.read_text(encoding='utf-8'))
        changed = False
        for profile in settings.get('machine_profiles', []):
            old = Path(profile['reference'])
            local = root / 'workspace/state/machine-references' / old.name
            if old.parent.name == 'machine-references' and local.is_file() and str(local) != str(old):
                profile['reference'] = str(local)
                changed = True
        if changed:
            temporary = settings_path.with_suffix('.portable.tmp')
            temporary.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding='utf-8')
            os.replace(temporary, settings_path)
    print('X-RAY DINO 2026-11-03 | Windows x64 | CPU', flush=True)
    print('本包預設啟用 47＋65 範例及參照圖＋待測圖雙圖判斷，與完整報告規則一致。', flush=True)
    print('資料儲存在此程式資料夾；請保持視窗開啟。', flush=True)
    import launch
    # Windows can allow another listener on a reused fixed port. An OS-selected
    # port avoids serving an older installation's page on this machine.
    bind = launch.bind_server
    launch.bind_server = lambda app: bind(app, ports=(0,))
    launch.main()
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        root = Path(sys.executable).resolve().parent
        (root / 'logs').mkdir(exist_ok=True)
        detail = traceback.format_exc()
        (root / 'logs/startup-error.txt').write_text(detail, encoding='utf-8')
        print(detail, file=sys.stderr)
        if sys.stdin and sys.stdin.isatty():
            input('啟動失敗，紀錄在 logs/startup-error.txt。按 Enter 關閉。')
        raise SystemExit(1)
