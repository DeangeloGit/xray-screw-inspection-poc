"""Create a new CPU-only 5r home from verified existing dependencies and 5r supplement."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('lean', 'reference-supplement', 'supplement', 'destination'):
        p.add_argument('--'+name, required=True, type=Path)
    a = p.parse_args()
    source, dest = a.supplement.resolve(), a.destination.resolve()
    if dest.exists():
        raise ValueError('Destination exists; never merge or overwrite')
    manifest = read(source/'SUPPLEMENT-MANIFEST.json')
    if manifest['format'] != 'XRAY-5R-MINIMAL-SUPPLEMENT-v1':
        raise ValueError('Wrong supplement')
    for row in manifest['files']:
        path = (source/row['path']).resolve()
        if not path.is_relative_to(source) or not path.is_file():
            raise ValueError('Missing or unsafe file: '+row['path'])
        with path.open('rb') as f:
            digest = hashlib.file_digest(f, 'sha256').hexdigest()
        if digest != row['sha256'] or path.stat().st_size != row['bytes']:
            raise ValueError('Supplement hash mismatch: '+row['path'])
    sys.path.insert(0, str(ROOT/'experiments/dino'))
    from live5r_review import ReviewBundle
    ReviewBundle(source/'home/local-review')
    subprocess.run([sys.executable, str(ROOT/'tools/prepare_5r_home.py'),
        '--lean', str(a.lean.resolve()), '--reference-supplement', str(a.reference_supplement.resolve()),
        '--destination', str(dest)], check=True)
    # These are new empty settings, not the user's existing station.
    settings = read(dest/'settings.json')
    shutil.copyfile(source/'home/default-reference.tiff', dest/'default-reference.tiff')
    settings['reference'] = str(dest/'default-reference.tiff')
    (dest/'settings.json').write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding='utf-8')
    ui = read(source/'home/station/state/ui_settings.json')
    refs = dest/'station/state/machine-references'
    shutil.copytree(source/'home/station/state/machine-references', refs)
    for profile in ui.get('machine_profiles', []):
        # Original paths can use Windows backslashes on a Mac restore.
        name = profile['reference'].replace('\\', '/').rsplit('/', 1)[-1]
        profile['reference'] = str(refs/name)
        if not (refs/name).is_file():
            raise ValueError('Missing machine reference: '+name)
    ui.update(dino_execution='cpu', allow_cpu_fallback=True, acquisition=dict(source='', enabled=False))
    (dest/'station/state/ui_settings.json').write_text(json.dumps(ui, ensure_ascii=False, indent=2), encoding='utf-8')
    shutil.copytree(source/'home/local-review', dest/'local-review')
    # Current main bank must match the source's active pointer and bytes.
    expected = read(source/'home/example-bank-hashes.json')
    for name, digest in expected.items():
        with (dest/'example-versions'/name).open('rb') as f:
            if hashlib.file_digest(f, 'sha256').hexdigest() != digest:
                raise ValueError('Reference supplement differs from validated 5r main bank: '+name)
    print(json.dumps(dict(status='passed', home=str(dest), inference_run=False,
        launch_env=dict(XRAY_5R_HOME=str(dest)), cpu=True, watching=False), ensure_ascii=False))

if __name__ == '__main__':
    main()
