"""Read-only verification and optional CPU smoke test of a lean 4r handoff.

All private inputs are resolved below --station. Runtime files and fresh results
go into a new --output directory outside that station. No ROOT/workspace alias,
old prediction cache, source annotations or existing verification record is used
as a substitute for inference.
"""
import argparse
import copy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
VERSION = 'dino-paired-optimized-47-20261104-r3'
ARM = 'curated_v5_review'
BANK_FILES = {
    'main': ('dino-4r-integrated-bank-20261106/curated_v5_review-bank.npz', (141, 8, 2, 384)),
    'visible_part': ('dino-4r-visible-screw-20261106/visible-part-bank.npz', (127, 8, 2, 384)),
    'complete_contour': ('dino-4r-example-audit-20261106/letterbox-112-bank.npz', (112, 8, 2, 384)),
    'normal_connector': ('dino-4r-connector-20261106/normal-connector-bank.npz', (1, 8, 2, 384)),
}
CASES = {'ng-128': [(10, 'keep'), (22, 'exclude'), (40, 'exclude')],
         'ng-135': [(88, 'keep')]}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def check_station(station, output):
    """Validate the formal contract, selected banks, and CPU/off defaults."""
    import numpy as np
    import station_transfer

    config_path = station / 'config/station.json'
    config = read(config_path)
    loc = station_transfer.layout(station, config_path)
    assert loc['work'] == (station / 'workspace').resolve(), 'Unexpected workspace layout'
    assert loc['models'] == (station / 'models').resolve(), 'Unexpected model layout'
    assert config.get('default_provider') == 'cpu', 'Station must default to CPU'
    assert config.get('allow_cpu_fallback') is True, 'CPU fallback must be enabled'
    ui_path = loc['work'] / 'state/ui_settings.json'
    ui = read(ui_path)
    assert ui.get('dino_execution', 'cpu') == 'cpu', 'UI must not request GPU'
    for name, settings in [('station', config), ('UI', ui)]:
        assert settings.get('acquisition', {}).get('enabled', False) is False, name + ' watcher must be off'
    validation = station_transfer.validate_station(station, work=loc['work'], models=loc['models'])
    assert validation['ok'], validation['errors']
    assert validation['model']['version'] == VERSION, 'Unexpected active model'

    model = station / 'models' / VERSION
    manifest = read(model / 'manifest.json')
    example_index = read(model / 'examples.json')
    seen = []
    paths = [config_path, ui_path, station / 'models/active.json',
             model / 'manifest.json', model / 'examples.json',
             model / manifest['file'], model / manifest['feature_file']]
    for label, count in [('screw', 47), ('normal', 65)]:
        identifiers = manifest['example_bank'][label]['ids']
        assert len(identifiers) == count
        for identifier in identifiers:
            row = example_index[identifier]
            source = model / 'examples' / row['file']
            assert source.is_file() and sha(source) == row['sha256'], identifier
            paths.append(source)
            seen.append(identifier)
    assert len(seen) == len(set(seen)) == 112

    archives = station / 'archives/workspace'
    banks, bank_info = {}, {}
    for name, (relative, expected_shape) in BANK_FILES.items():
        path = archives / relative
        with np.load(path, allow_pickle=False) as data:
            bank = data['bank'].copy()
            assert bank.shape == expected_shape and np.isfinite(bank).all(), (name, bank.shape)
            banks[name] = bank
            info = dict(path=relative, shape=list(bank.shape), sha256=sha(path))
            if name == 'main':
                count = int(data['n'])
                identifiers = data['ids'].tolist()
                assert count == 51 and len(identifiers) == len(set(identifiers)) == 141
                info.update(screw=count, normal=len(identifiers) - count, ids=identifiers)
            if name == 'normal_connector':
                aspect = float(data['aspect'])
                assert np.isfinite(aspect) and aspect > 0
                info['aspect'] = aspect
            bank_info[name] = info
        paths.append(path)
    active_root = archives / 'dino-4r-integrated-bank-20261106/active-reference-collection'
    active_manifest = read(active_root / 'manifest.json')
    assert len(active_manifest['examples']) == 141
    paths.append(active_root / 'manifest.json')
    for row in active_manifest['examples']:
        image_path = active_root / row['file']
        assert sha(image_path) == row['image_sha256'], row['id']
        assert hashlib.sha256(banks['main'][row['bank_index']].tobytes()).hexdigest() == row['feature_sha256']
        paths.append(image_path)
    part_images = list((archives / 'dino-4r-visible-screw-20261106/part-examples').glob('*.png'))
    assert len(part_images) == 15 and sum(p.name.startswith('positive-') for p in part_images) == 3
    paths.extend(part_images)
    paths.append(archives / 'dino-4r-connector-20261106/normal-example-22.png')
    part_config_path = archives / 'dino-4r-visible-screw-20261106/v3/experiment-plan.json'
    part_config = read(part_config_path)
    paths.append(part_config_path)
    for photo in CASES:
        folder = archives / 'dino-4r-crossbatch-20261106/runs' / photo
        paths.extend(folder / name for name in ('result.json', 'reference.png', 'aligned.png'))
    hashes = {str(p.relative_to(station)): sha(p) for p in paths}
    return dict(validation=validation, bank_info=bank_info, source_hashes=hashes,
                formal_examples_verified=112, integrated_examples_verified=141, additional_B_examples_verified=15), banks, part_config


def infer(station, output, checks, banks, part_config):
    """Run four specified checks with each photo's complete proposal support."""
    import cv2
    import numpy as np
    from PIL import Image
    from model_manager import ModelManager
    import example_audit_policy as base
    import integrated_bank_policy as integrated
    import connector_policy as terminal

    cv2.setNumThreads(4)
    model = ModelManager(station / 'models', allow_cpu=True, execution_override='cpu')
    original = model.snapshot(VERSION)
    assert not original.error, original.error
    assert original.session is not None
    providers = original.session.get_providers()
    assert providers == ['CPUExecutionProvider'], providers
    assert original.feature_bank.shape == (112, 8, 2, 384)
    manifest = copy.deepcopy(original.manifest)
    main_info = checks['bank_info']['main']
    manifest['example_bank']['screw']['ids'] = main_info['ids'][:51]
    manifest['example_bank']['normal']['ids'] = main_info['ids'][51:]
    manifest['model_id'] = 'DINO 4r lean continuation: 51 screw + 90 normal (' + ARM + ')'
    snapshot = replace(original, manifest=manifest, feature_bank=banks['main'])
    base.configure(banks['visible_part'], part_config, banks['complete_contour'])
    normal = dict(bank=banks['normal_connector'], aspect=checks['bank_info']['normal_connector']['aspect'])
    records = []
    archives = station / 'archives/workspace'
    for photo, selected in CASES.items():
        folder = archives / 'dino-4r-crossbatch-20261106/runs' / photo
        old = read(folder / 'result.json')
        candidates = sorted(old['candidates'] + old['filtered_candidates'], key=lambda row: row['id'])
        reference, target = [np.asarray(Image.open(folder / (name + '.png')).convert('L'), np.float32) / 255
                             for name in ('reference', 'aligned')]
        assert reference.shape == target.shape
        # Only proposal geometry/support is reused. The classifier removes prior
        # classification fields and computes fresh evidence from these images.
        objects = base.Objects(reference, target, candidates)
        by_id = {row['id']: row for row in candidates}
        for candidate_id, expected in selected:
            start = time.perf_counter()
            upstream = integrated.classify(snapshot, reference, target, by_id[candidate_id], objects)
            prediction, terminal_review = terminal.apply(snapshot, reference, target, upstream,
                                                         banks['complete_contour'], normal)
            pair = prediction['paired_evidence']
            actual = prediction['filter_recommendation']
            row = dict(photo=photo, candidate=candidate_id, expected=expected, verdict=actual,
                       passed=actual == expected, seconds=round(time.perf_counter() - start, 3),
                       support_candidates=len(candidates),
                       target_margin=pair['target']['screw_margin'],
                       reference_margin=pair['reference']['screw_margin'],
                       upstream_verdict=upstream['filter_recommendation'],
                       prediction=prediction, terminal_review=terminal_review)
            records.append(row)
            write(output / (photo + '-' + str(candidate_id) + '.json'), row)
            print(photo, '#' + str(candidate_id), actual, 'expected', expected, flush=True)
    return dict(providers=providers, formal_model=original.info(), cases=records,
                passed=all(row['passed'] for row in records),
                scope='Fresh CPU classification of four selected original-size cases only; '
                      'complete frozen proposal support, no proposal regeneration, no prediction/feature cache. '
                      'This is not a 100-image or 125%-scale regression, nor evidence of execution on another OS.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--station', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--infer', action='store_true', help='Run fresh CPU classification of the four checks')
    args = parser.parse_args()
    station, output = args.station.expanduser().resolve(), args.output.expanduser().resolve()
    if not station.is_dir():
        parser.error('Station does not exist')
    if output.exists() or output.is_relative_to(station):
        parser.error('Output must be a new directory outside the station')
    output.mkdir(parents=True)
    runtime = output / 'runtime'
    (runtime / 'state').mkdir(parents=True)
    config_path = output / 'probe-config.json'
    config = dict(schema_version=1, workspace=str(runtime), model_root=str(station / 'models'),
                  default_provider='cpu', allow_cpu_fallback=True,
                  acquisition=dict(source='', enabled=False))
    write(config_path, config)
    write(runtime / 'state/ui_settings.json', dict(dino_execution='cpu', allow_cpu_fallback=True,
                                                  acquisition=dict(source='', enabled=False)))
    os.environ['XRAY_CONFIG'] = str(config_path)
    os.environ['XRAY_WORKSPACE'] = str(runtime)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / 'experiments/dino'))
    result = dict(status='checking', station=str(station), infer_requested=args.infer,
                  host_platform=platform.platform(), python=sys.version.split()[0],
                  tool_sha256=sha(Path(__file__)), source_station_modified=False)
    try:
        checks, banks, part_config = check_station(station, output)
        result.update(checks)
        if args.infer:
            result['inference'] = infer(station, output, checks, banks, part_config)
        unchanged = all(sha(station / name) == digest for name, digest in checks['source_hashes'].items())
        result['checked_source_files_unchanged'] = unchanged
        assert unchanged, 'A checked source file changed during verification'
        assert not args.infer or result['inference']['passed'], 'Selected-case inference failed'
        result['status'] = 'passed'
        write(output / 'probe-result.json', result)
        print('PASS', 'four-case CPU smoke test' if args.infer else 'file/model/bank contract checks', flush=True)
        return 0
    except Exception as exc:
        result.update(status='failed', error=str(exc))
        write(output / 'probe-result.json', result)
        print('FAILED:', str(exc), file=sys.stderr, flush=True)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
