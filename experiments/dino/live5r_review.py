"""Versioned 5r alarm postreview, after the complete original detector run."""
import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from alarm_review5r import review_alarm


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def feature_sha(bank):
    return hashlib.sha256(np.ascontiguousarray(bank).tobytes()).hexdigest()


class ReviewBundle:
    def __init__(self, directory, *, allow_pending=False):
        self.directory = Path(directory).resolve()
        path = self.directory / 'manifest.json'
        self.meta = json.loads(path.read_text(encoding='utf-8'))
        if self.meta['schema_version'] != 1:
            raise ValueError('不支援的 5r 局部複核資料版本')
        if not allow_pending and self.meta['qualification']['status'] != 'passed':
            raise ValueError('5r 局部複核尚未通過驗證，不可啟用')
        for name, digest in self.meta['files'].items():
            source = (self.directory / name).resolve()
            if not source.is_relative_to(self.directory) or sha(source) != digest:
                raise ValueError('5r 局部複核檔案核對失敗：' + name)
        for name, digest in self.meta['policies'].items():
            source = Path(__file__).parent / name
            if source.name != name or sha(source) != digest:
                raise ValueError('5r 局部複核程式與驗證版本不同：' + name)
        with np.load(self.directory / 'additions.npz', allow_pickle=False) as data:
            self.positives = data['positive'].copy()
            self.normals = data['normal'].copy()
            self.positive_ids = data['positive_ids'].tolist()
            self.normal_ids = data['normal_ids'].tolist()
        with np.load(self.directory / 'visible-part.npz', allow_pickle=False) as data:
            self.parts = data['bank'].copy()
        for bank in (self.positives, self.normals, self.parts):
            if bank.ndim != 4 or bank.shape[1:] != (8, 2, 384) or not np.isfinite(bank).all():
                raise ValueError('5r 局部複核特徵不完整')
        if len(self.parts) != self.meta['part_screw'] + self.meta['part_normal'] or self.meta['part_screw'] != 50:
            raise ValueError('5r 可見局部庫正反例數不符')
        if len(self.positives) != len(self.positive_ids) or len(self.normals) != len(self.normal_ids):
            raise ValueError('5r 局部範例識別與特徵數不符')
        self.fingerprint = sha(path)

    def tagged_snapshot(self, base):
        identity = hashlib.sha256(('5r-local|' + base.identity + '|' + self.fingerprint).encode()).hexdigest()
        return replace(base, identity=identity)

    def trial_snapshot(self, base):
        if base.manifest['sha256'] != self.meta['model_sha256']:
            raise ValueError('5r 局部範例不適用於這個 DINO 模型')
        manifest = copy.deepcopy(base.manifest)
        screws = manifest['example_bank']['screw']['ids']
        normals = manifest['example_bank']['normal']['ids']
        ids = screws + self.positive_ids + normals + self.normal_ids
        if len(ids) != len(set(ids)):
            raise ValueError('5r 局部範例識別與主庫重複')
        n = len(screws)
        bank = np.concatenate([base.feature_bank[:n], self.positives,
                               base.feature_bank[n:], self.normals])
        manifest['example_bank']['screw']['ids'] = screws + self.positive_ids
        manifest['example_bank']['normal']['ids'] = normals + self.normal_ids
        manifest['model_id'] = f'5r 局部複核：{n+len(self.positives)} 螺絲＋{len(normals)+len(self.normals)} 正常'
        return replace(base, manifest=manifest, feature_bank=bank)

    def details(self, base):
        n = len(base.manifest['example_bank']['screw']['ids'])
        return dict(bundle=self.fingerprint, base_bank_matches_validation=feature_sha(base.feature_bank) == self.meta['base_feature_sha256'],
                    object_bank=dict(screw=n, normal=len(base.feature_bank)-n),
                    fragment_bank=dict(screw=n+len(self.positives), normal=len(base.feature_bank)-n+len(self.normals)),
                    visible_part_bank=dict(screw=50, normal=len(self.parts)-50))

    def apply(self, base, result, directory, review_bank, normal_bank):
        """Preserve original proposals/exclusions; update counts and overlays together."""
        import example_audit_policy as policy
        import visible_screw_policy_v3 as visible
        if directory is None:
            raise ValueError('5r 局部複核需要獨立的結果目錄')
        directory = Path(directory)
        original = copy.deepcopy(result)
        candidates = sorted(original['candidates'] + original['filtered_candidates'], key=lambda c: c['id'])
        if len(candidates) != original['pre_ai_count'] or len({c['id'] for c in candidates}) != len(candidates):
            raise ValueError('5r 原始候選覆蓋數不符')
        arrays = []
        for name in ('reference', 'aligned'):
            with Image.open(directory / (name + '.png')) as image:
                arrays.append(np.asarray(image.convert('L'), np.float32) / 255)
        trial = self.trial_snapshot(base)
        prior_parts, prior_config, prior_review = visible.BANK, visible.CONFIG, policy.BANK
        updated = copy.deepcopy(original)
        updated['candidates'], updated['filtered_candidates'] = [], []
        details = self.details(base)
        try:
            policy.configure(self.parts, prior_config, review_bank)
            for candidate in candidates:
                old = candidate['classification']
                pred = review_alarm(trial, *arrays, old, candidate, candidates, review_bank, normal_bank,
                                    core_snapshot=base)
                kept = pred['filter_recommendation'] == 'keep'
                if old['filter_recommendation'] == 'exclude' and pred != old:
                    raise ValueError('5r 不可更動原先已排除的候選')
                if old['filter_recommendation'] == 'keep':
                    pred['action'] = 'manual_review' if kept else 'discard'
                    pred['alarm_review5r']['banks'] = details
                    if 'visible_part_experiment' in pred:
                        pred['visible_part_experiment']['bank'] = f'50 screw / {len(self.parts)-50} normal'
                        for side in pred['paired_evidence'].values():
                            side['score_kind'] = f'exposed_part_50_positive_{len(self.parts)-50}_normal'
                updated['candidates' if kept else 'filtered_candidates'].append(dict(candidate, classification=pred))
        finally:
            policy.configure(prior_parts, prior_config, prior_review)
        updated['proposal_count'] = len(updated['candidates'])
        updated['filtered_count'] = len(updated['filtered_candidates'])
        updated['high_count'] = sum(c['priority'] == 'high' for c in updated['candidates'])
        updated['review_count'] = updated['proposal_count'] - updated['high_count']
        updated['wire_review_count'] = sum(bool(c.get('wire_review')) for c in updated['candidates'])
        encoded = json.dumps(original, ensure_ascii=False, sort_keys=True).encode('utf-8')
        baseline_name = 'baseline-4r-' + hashlib.sha256(encoded).hexdigest()[:16] + '.json'
        (directory / baseline_name).write_bytes(encoded)
        updated['local_review5r'] = dict(details, baseline_file=baseline_name,
                                       reviewed=len(original['candidates']), original_pipeline_completed=True)
        source = cv2.imdecode(np.fromfile(directory / 'source.png', dtype=np.uint8), cv2.IMREAD_COLOR)
        if source is None:
            raise ValueError('5r 缺少原圖預覽，不能更新警報疊圖')
        high, all_overlay = source.copy(), source.copy()
        for candidate in updated['candidates']:
            points = np.rint(np.asarray(candidate['source_polygon']) * updated['preview_scale']).astype('int32')
            color = (60, 65, 245) if candidate['priority'] == 'high' else (0, 185, 245)
            for canvas in ([high, all_overlay] if candidate['priority'] == 'high' else [all_overlay]):
                cv2.polylines(canvas, [points], True, color, 2)
                cv2.putText(canvas, str(candidate['id']), tuple(points.min(axis=0)-[0, 6]), cv2.FONT_HERSHEY_SIMPLEX, .6, color, 2)
        for name, image in [('overlay', high), ('all_overlay', all_overlay)]:
            ok, data = cv2.imencode('.png', image)
            if not ok:
                raise ValueError('5r 警報疊圖輸出失敗')
            temporary = directory / (name + '.5r.tmp')
            temporary.write_bytes(data.tobytes())
            temporary.replace(directory / (name + '.png'))
        return updated
