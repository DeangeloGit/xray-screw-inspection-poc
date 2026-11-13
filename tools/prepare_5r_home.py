"""Create a new isolated 5r home from verified Lean and reference restores."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lean', type=Path, required=True)
    parser.add_argument('--reference-supplement', type=Path, required=True)
    parser.add_argument('--source-home', type=Path, help='Copy machine profiles and thresholds only')
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    dest, lean, supplement = [p.resolve() for p in (args.destination, args.lean, args.reference_supplement)]
    if dest.exists():
        parser.error('Destination must not exist; existing stations are never merged')
    check = dest.parent / ('5r-preflight-'+uuid.uuid4().hex)
    subprocess.run([sys.executable, str(ROOT/'tools/lean_4r_probe.py'), '--station', str(lean), '--output', str(check)], check=True)
    assert read(check/'probe-result.json')['status'] == 'passed'
    manifest = read(supplement/'SUPPLEMENT-MANIFEST.json')
    assert manifest['format'] == 'XRAY-4R-REFERENCE-SUPPLEMENT-v1'
    for row in manifest['files']:
        path = (supplement/row['path']).resolve()
        assert path.is_relative_to(supplement) and path.is_file(), row['path']
        with path.open('rb') as stream:
            assert hashlib.file_digest(stream, 'sha256').hexdigest() == row['sha256'], row['path']
        assert path.stat().st_size == row['bytes'], row['path']
    config = dict(schema_version=1, workspace=str(dest/'station'), model_root=str(lean/'models'),
                  asset_root=str(lean/'archives'), default_provider='cpu', allow_cpu_fallback=True,
                  acquisition=dict(source='', enabled=False))
    settings = dict(dino_execution='cpu', allow_cpu_fallback=True, acquisition=dict(source='', enabled=False))
    # Validate all machine sources before creating the home.
    sources = []
    if args.source_home:
        source = args.source_home.resolve()
        old = read(source/'station/state/ui_settings.json')
        for profile in old.get('machine_profiles', []):
            profile = dict(profile)
            original = Path(profile['reference'])
            if not original.is_file(): raise ValueError('Missing reference: '+str(original))
            target = dest/'station/state/machine-references'/(profile['id']+original.suffix)
            profile['reference'] = str(target)
            sources.append((original, target, profile))
        settings.update(machine_profiles=[p for _, _, p in sources],
                        machine_thresholds=old.get('machine_thresholds', {}),
                        selected_machine=old.get('selected_machine', 'default'))
        original = Path(read(source/'settings.json')['reference'])
        if not original.is_file(): raise ValueError('Missing default reference: '+str(original))
        config['reference'] = str(dest/('default-reference'+original.suffix))
        sources.append((original, Path(config['reference']), None))
    dest.mkdir(parents=True)
    shutil.copytree(supplement/'example-home/example-versions', dest/'example-versions')
    (dest/'station/state').mkdir(parents=True)
    for original, target, _ in sources:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
    (dest/'settings.json').write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    (dest/'station/state/ui_settings.json').write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding='utf-8')
    (dest/'setup-verification.json').write_text(json.dumps(dict(lean_probe=str(check/'probe-result.json'),
        reference_manifest_files=len(manifest['files']), inference_run=False), indent=2), encoding='utf-8')
    print('5r isolated home ready:', dest)


if __name__ == '__main__':
    main()
