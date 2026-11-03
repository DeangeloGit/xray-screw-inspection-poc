"""Assemble the native Windows frozen build without modifying station data."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import subprocess
from urllib.parse import unquote, urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NAME = 'XRayReview-DINO-Paired-20261103-r2-Windows-x64'
OUT = ROOT / 'dist' / NAME
MODEL = 'dino-paired-47-20261103'
REPORT = ROOT / 'workspace/windows-check/diagnostics/dino-47-paired-full-20261103'


def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def write(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def assemble():
    if OUT.exists():
        raise FileExistsError('保留既有交付資料夾，請使用新的版本名稱：' + str(OUT))
    shutil.copytree(ROOT / 'build/frozen-dino-20261103-r2/XRayReview', OUT)
    for name in [MODEL, 'dino-examples-176c7281352c4e74', 'dino-examples-a3b8c97aa539', 'clip-examples-916f8a7fd458', 'noop-v1']:
        shutil.copytree(ROOT / 'models' / name, OUT / 'models' / name)
    write(OUT / 'models/active.json', dict(schema_version=1, version_directory=MODEL))
    write(OUT / 'config/station.json', dict(schema_version=1, station_id='DINO-PORTABLE-20261103',
        workspace='../workspace', model_root='../models', default_provider='cpu', allow_cpu_fallback=True,
        acquisition=dict(enabled=False, source='', poll_seconds=3, stable_seconds=15)))
    plan = json.loads((REPORT.parent / 'dino-full-evaluation-20261103/plan.json').read_text(encoding='utf-8'))
    profiles = []
    for machine, ref in plan['references'].items():
        source = Path(ref['path'])
        assert sha(source) == ref['sha256']
        relative = Path('workspace/state/machine-references') / (machine + source.suffix)
        (OUT / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, OUT / relative)
        profiles.append(dict(id=machine.lower(), name=machine, reference=str(relative), reference_name=source.name))
    write(OUT / 'workspace/state/ui_settings.json', dict(machine_profiles=profiles, selected_machine='mpt10',
        detection_threshold=.13, allow_cpu_fallback=True, acquisition=dict(enabled=False, source='')))
    (OUT / 'logs').mkdir(exist_ok=True)
    (OUT / '開始前請讀我.txt').write_text('''X-RAY DINO 可攜版｜2026-11-03｜Windows x64 CPU

1. 請完整解壓縮 ZIP 到可寫入的資料夾，例如 D:\\XRayReview。
2. 雙擊 XRayReview.exe；瀏覽器會開啟本機介面，請保持啟動視窗開啟。
3. 到工程頁面確認機種、正常參照圖、AI 模型，再選擇待測圖或來源資料夾。
4. 工程頁面 → AI 模型 → DINO 範例管理，可以查看、勾選及新增範例。
5. 關閉程式請在啟動視窗按 Ctrl+C。搬移時請複製整個資料夾。

不需另裝 Python，不需 NVIDIA 顯示卡；執行與範例更新可離線。
EXE 必須連同 _internal、models、config、workspace 一起保留，不可只複製 EXE。
首次內含 MPT10、MPT11、MPT12、KPH33 四種正常參照圖，差分門檻 0.13。
自動監看預設關閉；請自行指定此電腦上的來源，再啟用。

此包預設模型：DINO 雙圖（47 張螺絲＋65 張正常）。兩個條件同時啟用。
判斷方式：參照小圖與待測小圖各自找最像的 3 張螺絲、3 張正常範例，比較兩邊平均相似程度。
保留原版 DINO（31＋65）與 CLIP 螺絲外型範例版，供工程頁面切換。
待測圖像螺絲、參照圖不像螺絲才保留；兩圖都像螺絲或待測圖不像螺絲則排除。
這與完整報告的雙圖版本相同：固定候選重播為良品剩 0 框、不良品剩 386 框。
已知有疑似誤刪風險，詳見版本總結；功能仍依使用者要求啟用。

資料與設定保存在本資料夾；沒有複製開發機的監看路徑、舊人工紀錄或結果資料庫。
完整圖資報告另附 ZIP，解壓後開啟「開啟完整報告.html」。
如需檢查此電腦是否可執行，雙擊 DIAGNOSTICS.cmd，結果在 logs\\portable-selftest.json。
模型與 X 光範例包含私人圖資，交付包沒有上傳公開網站。
''', encoding='utf-8-sig')
    (OUT / 'DIAGNOSTICS.cmd').write_text('@echo off\ncd /d "%~dp0"\nXRayReview.exe --self-test\necho.\necho See logs\\portable-selftest.json\npause\n', encoding='ascii')
    shutil.copyfile(ROOT / 'docs/DINO_PAIRED_RELEASE_20261103.html', OUT / '版本總結.html')
    (OUT / 'licenses').mkdir()
    shutil.copyfile(Path(subprocess.check_output([str(ROOT / '.venv/Scripts/python.exe'), '-c', 'import sys;print(sys.base_prefix)'], text=True).strip()) / 'LICENSE.txt', OUT / 'licenses/PYTHON-LICENSE.txt')
    # Keep actual installed package metadata, including available license texts.
    for site in [ROOT / '.venv/Lib/site-packages', ROOT / 'build/pyinstaller-tools']:
        for info in site.glob('*.dist-info'):
            shutil.copytree(info, OUT / 'licenses' / info.name, dirs_exist_ok=True)
    for name in ['DINO_DEVELOPMENT.md', 'DINO_EXAMPLES_UI.md', 'UI_WORKFLOW.md']:
        shutil.copyfile(ROOT / 'docs' / name, OUT / name)
    sources = [*ROOT.glob('*.py'), *ROOT.glob('templates/*'), *ROOT.glob('static/*'),
               ROOT / 'packaging/frozen_entry.py', ROOT / 'packaging/portable_release_check.py']
    write(OUT / 'BUILD-MANIFEST.json', dict(version=NAME, source_commit=subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), includes_uncommitted_work=True,
        python='3.14.3', pyinstaller='6.22.3', platform='Windows x64 CPU', default_model=MODEL,
        reference_pair_rule_enabled=True, source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sources if p.is_file()}))
    print('Assembled: ' + str(OUT), flush=True)


class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links = []
    def handle_starttag(self, tag, attrs):
        self.links.extend(v for k,v in attrs if k in ('href','src') and v)


def report():
    destination = ROOT / 'dist/XRayReview-DINO-Paired-20261103-r2-完整報告'
    destination.mkdir(parents=True, exist_ok=False)
    base = REPORT.parent.resolve()
    pending = [REPORT / 'index.html']
    visited = set()
    while pending:
        source = pending.pop().resolve()
        if source in visited:
            continue
        assert source.is_relative_to(base), str(source)
        assert source.is_file(), str(source)
        visited.add(source)
        target = destination / source.relative_to(base)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if source.suffix == '.html':
            parser = Links(); parser.feed(source.read_text(encoding='utf-8'))
            for link in parser.links:
                url = urlsplit(link)
                if url.scheme or url.netloc or not url.path:
                    continue
                pending.append(source.parent / unquote(url.path))
    (destination / '開啟完整報告.html').write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=dino-47-paired-full-20261103/index.html"><a href="dino-47-paired-full-20261103/index.html">開啟完整報告</a>', encoding='utf-8')
    shutil.copyfile(ROOT / 'docs/DINO_PAIRED_RELEASE_20261103.html', destination / '版本總結.html')
    write(destination / 'REPORT-MANIFEST.json', dict(photos=190, candidates=2793, copied_files=len(visited),
        file_sha256={str(p.relative_to(destination)):sha(p) for p in destination.rglob('*') if p.is_file()}))
    print('Report files: ' + str(len(visited)), flush=True)
    archive(destination)


def archive(directory):
    path = directory.with_suffix('.zip')
    if path.exists():
        raise FileExistsError(path)
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zip:
        for f in directory.rglob('*'):
            if f.is_file():
                zip.write(f, f.relative_to(directory.parent))
    with zipfile.ZipFile(path) as zip:
        assert zip.testzip() is None
    path.with_suffix('.zip.sha256').write_text(sha(path) + '  ' + path.name + '\n', encoding='utf-8')
    print(json.dumps(dict(file=str(path), MB=round(path.stat().st_size/1024**2,1), sha256=sha(path)), ensure_ascii=False), flush=True)


def seal():
    check = json.loads((OUT / 'logs/portable-selftest.json').read_text(encoding='utf-8'))
    assert check['success'] and not check.get('error'), check
    p = OUT / 'BUILD-MANIFEST.json'
    manifest = json.loads(p.read_text(encoding='utf-8'))
    for name in ['packaging/frozen_entry.py', 'packaging/portable_release_check.py']:
        manifest['source_sha256'][name] = sha(ROOT / name)
    manifest['windows_execution_verified'] = True
    manifest['verification'] = check['checks']
    parity = json.loads((ROOT / 'workspace/dino-paired-release-20261103/verification.json').read_text(encoding='utf-8'))
    assert parity['success'] and parity['candidates'] == 2793 and parity['kept'] == {'OK': 0, 'NG': 386}
    assert check['model']['fingerprint'] == parity['fingerprint']
    write(OUT / 'logs/report-parity.json', parity)
    manifest['report_parity'] = parity
    manifest['file_sha256'] = {str(f.relative_to(OUT)):sha(f) for f in OUT.rglob('*') if f.is_file() and f != p}
    write(p, manifest)
    archive(OUT)


if __name__ == '__main__':
    import sys
    if '--report' in sys.argv:
        report()
    elif '--archive' in sys.argv:
        seal()
    else:
        assemble()
