"""Fresh r3/4r detection from a frozen new-batch plan; never reads answer labels.

Usage: python experiments/dino/new_model_run.py OUTPUT --provider gpu
All runtime settings and results are isolated under OUTPUT. Model/example files
are read-only inputs; this runner does not build banks, tune thresholds, or score.
"""
import argparse
from collections import OrderedDict
import contextlib
import copy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid


ROOT = Path(__file__).resolve().parents[2]
MODEL = 'dino-paired-optimized-47-20261104-r3'
ARM = 'curated_v5_review'
VERSION = 'new-batch-frozen-r3-integrated-4r-20261109'
BANK_FILES = {
    'main': 'dino-4r-integrated-bank-20261106/curated_v5_review-bank.npz',
    'visible': 'dino-4r-visible-screw-20261106/visible-part-bank.npz',
    'review': 'dino-4r-example-audit-20261106/letterbox-112-bank.npz',
    'connector': 'dino-4r-connector-20261106/normal-connector-bank.npz',
    'part_config': 'dino-4r-visible-screw-20261106/v3/experiment-plan.json',
}
POLICY_FILES = [
    'detector.py', 'detection_runtime.py', 'model_manager.py',
    'dino_paired_optimized.py', 'dino_adapter.py', 'overkill_pilot.py',
    'paired_geometry.py', 'single_reference_evidence.py', 'wire_review.py',
    'gpu_runtime.py', 'gpu_worker.py', 'gpu_devices.py',
] + ['experiments/dino/' + name + '.py' for name in (
    'new_model_run', 'integrated_bank_policy', 'example_audit_policy',
    'visible_screw_policy_v3', 'visible_screw_geometry_v2',
    'correspondence_policy', 'correspondence_geometry', 'stability_policy',
    'improvement_policy', 'connector_policy',
)]


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def unchanged(hashes):
    changed = [str(p) for p, digest in hashes.items() if not Path(p).is_file() or sha(p) != digest]
    if changed:
        raise ValueError('Frozen inputs changed: ' + ', '.join(changed[:12]))


class TensorCache:
    """Bounded RAM-only exact ONNX-input reuse, cleared for every photo/run."""
    def __init__(self, session, model_identity, limit=384):
        self.session, self.model_identity, self.limit = session, model_identity, limit
        self.clear()

    def __getattr__(self, key):
        return getattr(self.session, key)

    def clear(self):
        self.values = OrderedDict()
        self.hits = self.fresh = 0

    def run(self, outputs, inputs):
        import numpy as np
        tensor_keys = []
        for name, value in sorted(inputs.items()):
            value = np.ascontiguousarray(value)
            tensor_keys.append((name, value.shape, value.dtype.str,
                                hashlib.sha256(value.tobytes()).hexdigest()))
        key = (self.model_identity, None if outputs is None else tuple(outputs), tuple(tensor_keys))
        if key in self.values:
            self.hits += 1
            self.values.move_to_end(key)
            return self.values[key]
        value = self.session.run(outputs, inputs)
        self.fresh += 1
        self.values[key] = value
        if len(self.values) > self.limit:
            self.values.popitem(last=False)
        return value


def load_banks(original):
    import numpy as np
    import example_audit_policy as policy
    from dino_paired_optimized import validate_bank
    paths = {key: ROOT / 'workspace' / relative for key, relative in BANK_FILES.items()}
    loaded = {}
    for key in ('main', 'visible', 'review', 'connector'):
        with np.load(paths[key], allow_pickle=False) as data:
            loaded[key] = {name: data[name].copy() for name in data.files}
    main = loaded['main']
    ids = main['ids'].tolist()
    if int(main['n']) != 51 or len(ids) != 141 or len(set(ids)) != 141:
        raise ValueError('Frozen MAIN bank must be 51 screw + 90 normal, with unique IDs')
    for name, count in (('main', 141), ('visible', 127), ('review', 112), ('connector', 1)):
        bank = loaded[name]['bank']
        if (bank.shape != (count, 8, 2, 384) or not np.isfinite(bank).all()
                or not np.allclose(np.linalg.norm(bank, axis=-1), 1, atol=.001)):
            raise ValueError('Invalid frozen bank: ' + name)
        bank.flags.writeable = False
    config = read(paths['part_config'])
    if config['target_min'] != .05:
        raise ValueError('Frozen visible-part confidence changed')
    aspect = float(loaded['connector']['aspect'])
    if not np.isfinite(aspect) or aspect <= 0:
        raise ValueError('Invalid connector exemplar aspect')
    policy.configure(loaded['visible']['bank'], config, loaded['review']['bank'])
    manifest = copy.deepcopy(original.manifest)
    manifest['example_bank']['screw']['ids'] = ids[:51]
    manifest['example_bank']['normal']['ids'] = ids[51:]
    manifest['model_id'] = 'DINO 4r frozen experiment: 51 screw + 90 normal (' + ARM + ')'
    # Preserve the r3 feature_sha256 compatibility gate used by proposal recovery.
    # Actual replaced features and ALL banks are explicitly identified separately.
    manifest['experimental_main_bank_sha256'] = sha(paths['main'])
    bank = validate_bank(manifest, main['bank'])
    details = dict(arm=ARM, main_positive=51, main_normal=90,
                   visible_positive=50, visible_normal=77, review_positive=47, review_normal=65,
                   connector_normal=1, paths={k: str(v) for k, v in paths.items()},
                   hashes={str(v): sha(v) for v in paths.values()},
                   main_ids=ids, part_target_min=config['target_min'], connector_aspect=aspect,
                   production_feature_gate_preserved=True, production_model_modified=False)
    return manifest, bank, loaded['review']['bank'], dict(bank=loaded['connector']['bank'], aspect=aspect), details


@contextlib.contextmanager
def four_r(detector, pilot, snapshot, review_bank, normal_bank):
    """Same fresh proposal recipe as crossbatch_run, then the frozen final policy."""
    import numpy as np
    import example_audit_policy as policy
    import improvement_policy
    import integrated_bank_policy as integrated
    import connector_policy as terminal
    from detection_runtime import CURRENT
    original_proposals, original_check = detector.proposals, detector.check_candidate
    original_classify, original_overlap, original_apply = (
        detector.classify_dino_candidate, pilot.overlapping, pilot.apply)
    state = {}

    def proposals(ref, target, mask, threshold, structure_changes=None, similarity_recoveries=None):
        if similarity_recoveries is None:
            raise ValueError('4r requires enabled pilot proposal recovery')
        predicted = detector.compensate_brightness(ref, target)
        cs, residual = original_proposals(ref, target, mask, threshold,
                                          structure_changes, similarity_recoveries, predicted=predicted)
        cs += improvement_policy.supplemental(
            ref, target, mask, predicted,
            cs + list(similarity_recoveries))
        oldadd = []
        for candidate in sorted(similarity_recoveries, key=lambda c: -c['score']):
            if not original_overlap(candidate, cs):
                checked, explained = original_check(ref, target, copy.deepcopy(candidate), threshold)
                state.setdefault('recovery_checks', {})[id(candidate)] = (checked, explained)
                if not explained:
                    oldadd.append(checked)
        qr, qt = CURRENT.get().arrays(ref, target)
        existing_boxes = {policy.box(c) for c in cs + oldadd}
        extras = []
        for part in policy.geometry.proposals(qr, qt):
            part = {k: v for k, v in part.items() if k != 'mask'}
            x, y, w, h = part['box']
            if tuple(part['box']) in existing_boxes:
                continue
            extras.append(dict(x=x, y=y, w=w, h=h, area=part['area'], score=-1.,
                               normal_support=0., aspect=max(w, h) / min(w, h),
                               fill=part['area'] / (w * h), bipolar=0.,
                               contrast=part['mean_difference'], shape_similarity=0.,
                               recovery='r4_visible_part', change_type='visible_screw_candidate',
                               visible_part=part))
        similarity_recoveries.extend(extras)
        # All same-photo support is available BEFORE sequential classification.
        state['objects'] = policy.Objects(qr, qt, cs + oldadd + extras)
        return cs, residual

    def classify(_snapshot, target, ref, candidate):
        pred = integrated.classify(snapshot, ref, target, candidate, state['objects'])
        context = CURRENT.get()
        if context is None:
            raise ValueError('Fresh detector context is required')
        qr, qt = context.arrays(ref, target)
        # Frozen final replay used saved PNG arrays; match that quantization.
        pred, _check = terminal.apply(snapshot, qr, qt, pred, review_bank, normal_bank,
                                      decision_only=os.environ.get('XRAY_5R_LOCAL_REVIEW') == '1')
        # Keep upstream old_kept unchanged: terminal filtering must not alter
        # the established visible-part duplicate-suppression semantics.
        return pred

    def check_candidate(ref, target, candidate, threshold):
        if candidate.get('recovery') == 'r4_visible_part':
            return candidate, False
        cached = state.get('recovery_checks', {}).get(id(candidate))
        if cached is not None:
            return copy.deepcopy(cached[0]), cached[1]
        return original_check(ref, target, candidate, threshold)

    try:
        detector.check_candidate = check_candidate
        pilot.overlapping = lambda c, previous: (any(policy.box(c) == policy.box(p) for p in previous)
                                                 if c.get('recovery') == 'r4_visible_part'
                                                 else original_overlap(c, previous))
        detector.proposals, detector.classify_dino_candidate = proposals, classify
        # The frozen policy already calls the original pilot internally.
        pilot.apply = lambda snap, ref, tar, c, pred: pred
        yield
    finally:
        detector.proposals, detector.check_candidate = original_proposals, original_check
        detector.classify_dino_candidate = original_classify
        pilot.overlapping, pilot.apply = original_overlap, original_apply


def validate_result(result, folder):
    candidates = result['candidates'] + result['filtered_candidates']
    assert len(candidates) == result['pre_ai_count']
    assert len(result['candidates']) == result['proposal_count']
    assert len(result['filtered_candidates']) == result['filtered_count']
    assert len({c['id'] for c in candidates}) == len(candidates)
    assert all(c['classification']['status'] == 'active' for c in candidates)
    assert all(c['classification']['filter_recommendation'] == 'keep' for c in result['candidates'])
    assert all(c['classification']['filter_recommendation'] == 'exclude' for c in result['filtered_candidates'])
    for name in ('source', 'reference', 'aligned', 'overlay', 'all_overlay', 'difference'):
        assert (folder / (name + '.png')).is_file(), name
    for candidate in candidates:
        for prefix in ('crop_', 'reference_crop_'):
            assert (folder / (prefix + str(candidate['id']) + '.png')).is_file()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--provider', choices=('gpu', 'cpu'), default='gpu')
    args = parser.parse_args()
    out = args.output.expanduser().resolve()
    plan_path = out / 'plan.json'
    plan = read(plan_path)
    plan_sha = sha(plan_path)
    if plan['methods'] != ['r3', '4r'] or plan['model']['requested'] != MODEL or plan['threshold'] != .13:
        raise ValueError('Expected frozen r3/4r plan, r3 model, threshold .13')
    keys = [row['key'] for row in plan['items']]
    if not keys or len(set(keys)) != len(keys) or any(
            not isinstance(k, str) or not k or Path(k).name != k or k in ('.', '..') or '\\' in k or '/' in k
            for k in keys):
        raise ValueError('Plan photo keys must be unique safe directory names')
    protected = dict(plan['hashes'])
    protected[str(plan_path)] = plan_sha
    for row in plan['items']:
        if sha(row['path']) != row['sha256']:
            raise ValueError('Photo SHA differs from plan: ' + row['key'])
        protected[str(Path(row['path']).resolve())] = row['sha256']
        reference = Path(row['reference']).resolve()
        if str(reference) not in protected:
            raise ValueError('Reference image must be frozen in plan.hashes: ' + str(reference))
    unchanged(protected)
    # Set isolation before importing any runtime module (which creates dirs).
    runtime, config_path = out / 'runtime', out / 'isolated-settings.json'
    config = dict(schema_version=1, workspace=str(runtime), model_root=str(ROOT / 'models'),
                  default_provider='cpu', allow_cpu_fallback=True,
                  acquisition=dict(source='', enabled=False))
    if config_path.exists() and read(config_path) != config:
        raise ValueError('Existing isolated runtime configuration differs')
    if not config_path.exists():
        save(config_path, config)
    os.environ['XRAY_CONFIG'], os.environ['XRAY_WORKSPACE'] = str(config_path), str(runtime)
    os.environ['XRAY_OVERKILL_PILOT'] = '0'
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / 'experiments/dino'))
    import cv2
    import detector
    import overkill_pilot as pilot
    import integrated_bank_policy as integrated
    import connector_policy as terminal
    from model_manager import ModelManager
    cv2.setNumThreads(4)
    current = None
    session = None
    try:
        original = ModelManager(ROOT / 'models', allow_cpu=True,
                                execution_override=args.provider).snapshot(MODEL)
        if original.error or original.session is None or original.info()['execution'] != args.provider:
            raise ValueError('Requested execution unavailable: ' + str(original.info()))
        session = original.session
        if [len(original.manifest['example_bank'][k]['ids']) for k in ('screw', 'normal')] != [47, 65]:
            raise ValueError('Original r3 bank must remain 47+65')
        manifest, main_bank, review_bank, normal_bank, bank_info = load_banks(original)
        owned_inputs = {str(ROOT / path): sha(ROOT / path) for path in POLICY_FILES}
        owned_inputs.update(bank_info['hashes'])
        for name in ('manifest.json', 'model.onnx', 'paired-features.npz', 'examples.json'):
            path = ROOT / 'models' / MODEL / name
            owned_inputs[str(path)] = sha(path)
        frozen = dict(protected)
        for path, digest in owned_inputs.items():
            if path in frozen and frozen[path] != digest:
                raise ValueError('Run input differs from plan: ' + path)
            frozen[path] = digest
        unchanged(frozen)
        common = dict(runner=VERSION, runner_sha256=sha(Path(__file__)), plan_sha256=plan_sha,
                      provider=args.provider, providers=original.session.get_providers(),
                      original_model=original.info(), actual_4r_banks=bank_info,
                      policy_versions=dict(integrated=integrated.VERSION, terminal=terminal.VERSION),
                      run_input_hashes=owned_inputs, fresh_full_detection=True,
                      reused_previous_candidates=False, reused_disk_feature_cache=False,
                      answers_used_for_inference=False, production_changed=False)
        method_ids = {method: identity(dict(common, method=method)) for method in plan['methods']}
        execution = dict(common, method_identities=method_ids)
        execution_path = out / 'execution.json'
        if execution_path.exists() and read(execution_path) != execution:
            raise ValueError('Execution inputs changed; use a new output directory')
        save(execution_path, execution)
        cache = TensorCache(original.session, original.identity)
        original = replace(original, session=cache)
        experimental = replace(original, manifest=manifest, feature_bank=main_bank,
                               identity=method_ids['4r'])
        receipts = []
        for method in plan['methods']:
            os.environ['XRAY_OVERKILL_PILOT'] = '0' if method == 'r3' else '1'
            snap = original if method == 'r3' else experimental
            assert pilot.enabled(snap) == (method == '4r')
            patch = contextlib.nullcontext() if method == 'r3' else four_r(
                detector, pilot, experimental, review_bank, normal_bank)
            with patch:
                for number, row in enumerate(plan['items'], 1):
                    current = dict(method=method, key=row['key'])
                    folder = out / 'runs' / method / row['key']
                    complete = folder / 'complete.json'
                    if complete.exists():
                        receipt = read(complete)
                        assert receipt['plan_sha256'] == plan_sha
                        assert receipt['method_identity'] == method_ids[method]
                        assert receipt['result_sha256'] == sha(folder / 'result.json')
                        assert receipt['method'] == method and receipt['key'] == row['key']
                        validate_result(read(folder / 'result.json'), folder)
                        receipts.append(receipt)
                        print('RESUME', method, row['key'], flush=True)
                        continue
                    if (out / 'run-complete.json').exists():
                        raise ValueError('Completed batch is missing a photo receipt; do not overwrite evidence')
                    cache.clear()
                    started = time.perf_counter()
                    result = detector.detect(row['reference'], row['path'], row['key'], plan['threshold'],
                                             model_snapshot=snap, output_directory=folder)
                    result['validation_method'] = method
                    result['validation_method_identity'] = method_ids[method]
                    if method == '4r':
                        result['proposal_recovery_policy'] = result.get('experimental_policy')
                        result['experimental_policy'] = integrated.VERSION + ' + ' + terminal.VERSION
                        result['experimental_main_bank'] = dict(arm=ARM, screw=51, normal=90,
                            sha256=manifest['experimental_main_bank_sha256'])
                        result['production_changed'] = False
                    else:
                        assert 'experimental_policy' not in result
                    validate_result(result, folder)
                    save(folder / 'result.json', result)
                    assert sha(plan_path) == plan_sha
                    receipt = dict(key=row['key'], method=method, plan_sha256=plan_sha,
                                   method_identity=method_ids[method], provider=args.provider,
                                   actual_providers=cache.get_providers(), model=result['model'],
                                   seconds=round(time.perf_counter() - started, 3),
                                   candidates=result['pre_ai_count'], kept=result['proposal_count'],
                                   excluded=result['filtered_count'], result_sha256=sha(folder / 'result.json'),
                                   fresh_full_detection=True, fresh_onnx_calls=cache.fresh,
                                   exact_tensor_cache_hits=cache.hits)
                    save(complete, receipt)
                    receipts.append(receipt)
                    print('FULL', method, number, '/', len(plan['items']), row['key'],
                          'candidates', receipt['candidates'], 'keep', receipt['kept'],
                          'seconds', receipt['seconds'], flush=True)
        unchanged(frozen)
        assert len(receipts) == len(plan['items']) * len(plan['methods'])
        save(out / 'run-complete.json', dict(complete=True, fresh_full_detection=True,
             source_and_production_hashes_unchanged=True, plan_sha256=plan_sha,
             method_identities=method_ids, methods=plan['methods'], photos=len(plan['items']),
             method_photo_runs=len(receipts), provider=args.provider,
             actual_providers=cache.get_providers(), answers_used_for_inference=False,
             reused_previous_candidates=False, reused_disk_feature_cache=False,
             execution_sha256=sha(execution_path), receipt_hashes={
                 method + '/' + key: sha(out / 'runs' / method / key / 'complete.json')
                 for method in plan['methods'] for key in keys}))
        print('COMPLETE', len(plan['items']), 'photos, r3 + frozen 4r, provider', args.provider, flush=True)
        return 0
    except Exception as exc:
        save(out / 'run-failed.json', dict(status='failed', current=current,
             error=type(exc).__name__ + ': ' + str(exc), plan_sha256=plan_sha,
             provider=args.provider, complete=False))
        raise
    finally:
        if session is not None and hasattr(session, 'close'):
            session.close()


if __name__ == '__main__':
    raise SystemExit(main())
