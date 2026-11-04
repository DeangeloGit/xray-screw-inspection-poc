"""Build a native app for this Mac, retaining its existing station workspace."""
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.platform != 'darwin':
        raise SystemExit('Run this builder on macOS.')
    stage = ROOT / 'build/mac'
    stage.mkdir(parents=True, exist_ok=True)
    # Separate config avoids changing the station's existing configuration.
    original = ROOT / 'config/station.json'
    if original.exists():
        config = original
    else:
        config = stage / 'station.json'
        config.write_text(json.dumps(dict(
            schema_version=1, station_id='MACBOOK', workspace=str(ROOT),
            model_root=str(ROOT / 'models'), default_provider='cpu',
            allow_cpu_fallback=True,
            acquisition=dict(enabled=False, source='', poll_seconds=3, stable_seconds=15)
        ), indent=2), encoding='utf-8')
    defaults = stage / 'mac-defaults.json'
    defaults.write_text(json.dumps(dict(config=str(config), workspace=str(ROOT))), encoding='utf-8')
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
               '--windowed', '--name', 'XRayReview-Mac', '--target-arch', platform.machine(),
               '--osx-bundle-identifier', 'local.xray.review',
               '--paths', str(ROOT), '--distpath', str(ROOT / 'dist'),
               '--workpath', str(stage / 'pyinstaller'), '--specpath', str(stage),
               '--collect-all', 'onnxruntime', '--hidden-import', 'launch']
    for source in [ROOT / 'templates', ROOT / 'static', defaults]:
        command.extend(['--add-data', str(source) + ':.']) if source.is_file() else command.extend([
            '--add-data', str(source) + ':' + source.name])
    command.append(str(ROOT / 'packaging/mac_entry.py'))
    subprocess.run(command, cwd=ROOT, check=True)
    bundle = Path.home() / 'Applications/XRayReview-Mac.app'
    bundle.parent.mkdir(parents=True, exist_ok=True)
    # Documents can regenerate Finder metadata; install and sign outside that tree.
    subprocess.run(['ditto', '--noextattr', '--norsrc',
                    str(ROOT / 'dist/XRayReview-Mac.app'), str(bundle)], check=True)
    subprocess.run(['xattr', '-cr', str(bundle)], check=True)
    subprocess.run(['codesign', '--force', '--deep', '--sign', '-', str(bundle)], check=True)
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(bundle)], check=True)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    (stage / 'build.json').write_text(json.dumps(dict(
        source_commit=commit, architecture=platform.machine(), python=sys.version,
        workspace=str(ROOT), config=str(config),
        model_status='Existing external models; DINO requires private model restoration.'
    ), indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
