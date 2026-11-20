"""Fail-closed, suggestion-only integration of the confirmed MPT10 U1 review.

Reference annotations never modify detections, classifications or overlays.
The optional reference package is pinned in station settings. A missing or
invalid package disables this advisory stage, not the completed base detector.
"""
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image
import confirmed_local_reference_shadow5r as policy

VERSION = '5r-confirmed-U1-suggestions-20261120'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class LocalReferenceReview:
    def __init__(self, directory, expected_sha256):
        self.directory = Path(directory).resolve()
        self.expected_sha256 = expected_sha256

    def load(self):
        path = self.directory/'manifest.json'
        if not self.expected_sha256 or sha(path) != self.expected_sha256:
            raise ValueError('局部參照清單未設定或SHA不符')
        meta = json.loads(path.read_text(encoding='utf8'))
        if (meta.get('schema_version') != 1 or meta.get('mode') != 'suggestion_only'
            or meta.get('machine') != 'MPT10' or meta.get('automatic_exclusion') is not False
            or meta.get('scope') != 'confirmed_U1_only' or len(meta['references']) != 2):
            raise ValueError('局部參照範圍或模式不符')
        for name, digest in meta['policies'].items():
            if Path(name).name != name or sha(Path(__file__).parent/name) != digest:
                raise ValueError('局部參照複核版本不符')
        images = {}
        seen = set()
        for ref in meta['references']:
            if (ref['machine'] != 'MPT10' or ref['reference_sha256'] != meta['reference_sha256']
                or ref.get('local_normal_confirmed') is not True
                or ref.get('whole_image_normal_confirmed') is not False
                or ref['source_sha256'] in seen):
                raise ValueError('局部人工確認不完整或來源重複')
            seen.add(ref['source_sha256'])
            for key, digest_key in [('source_file','source_sha256'),('aligned_file','aligned_sha256')]:
                file = (self.directory/ref[key]).resolve()
                if not file.is_relative_to(self.directory) or sha(file) != ref[digest_key]:
                    raise ValueError('局部參照檔案缺失或SHA不符')
            with Image.open(self.directory/ref['aligned_file']) as im:
                images[ref['id']] = np.asarray(im.convert('L'),np.float32)/255
            x,y,X,Y = ref['confirmed_normal_bbox']
            h,w = images[ref['id']].shape
            if not all(type(n) is int for n in (x,y,X,Y)) or not (0<=x<X<=w and 0<=y<Y<=h):
                raise ValueError('局部確認範圍無效')
        return meta, images

    def status(self):
        try:
            meta, _ = self.load()
            return dict(version=VERSION,mode='suggestion_only',ready=True,
                        machine='MPT10',scope=meta['scope'],manifest_sha256=self.expected_sha256,
                        automatic_exclusion=False)
        except Exception as error:
            return dict(version=VERSION,mode='suggestion_only',ready=False,
                        automatic_exclusion=False,reason=str(error))

    def apply(self, result, directory, reference_path, target_path):
        directory = Path(directory)
        evidence = dict(version=VERSION,mode='suggestion_only',automatic_exclusion=False,
                        original_alarms_preserved=True,rows=[],suggested_exclusions=[])
        try:
            meta, images = self.load()
            reference_sha = sha(reference_path)
            if reference_sha != meta['reference_sha256']:
                evidence.update(status='not_applicable',reason='不同機種／參照版本，不套用U1複核')
            elif not result.get('matrix') or not np.isfinite(np.asarray(result['matrix'],float)).all():
                evidence.update(status='unavailable',reason='對位資料無效，保留原判')
            else:
                query = dict(machine='MPT10',reference_sha256=reference_sha,source_sha256=sha(target_path))
                with Image.open(directory/'reference.png') as im:
                    reference = np.asarray(im.convert('L'),np.float32)/255
                with Image.open(directory/'aligned.png') as im:
                    target = np.asarray(im.convert('L'),np.float32)/255
                if reference.shape != target.shape:
                    raise ValueError('對位影像尺寸不符')
                evidence['rows'] = [policy.review(reference,target,c,meta['references'],query,
                                                 lambda r:images[r['id']]) for c in result['candidates']]
                evidence.update(status='completed',manifest_sha256=self.expected_sha256,
                                alignment_warning=bool(result.get('alignment_warning')),
                                alignment_note='整圖警告另列；局部複核須分別通過原對位條件')
                evidence['suggested_exclusions'] = [r['candidate_id'] for r in evidence['rows']
                                                   if r['recommendation']=='exclude_suggestion']
        except Exception as error:
            evidence.update(status='unavailable',reason=str(error),rows=[],suggested_exclusions=[])
        # This function only adds top-level metadata; never edits a candidate.
        updated = copy.deepcopy(result)
        summary = {k:v for k,v in evidence.items() if k!='rows'}
        try:
            path = directory/'confirmed-local-suggestions.json'
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf8')
            temporary.replace(path)
            summary['evidence_file'] = path.name
        except OSError as error:
            summary.update(status='unavailable',reason='建議證據無法寫入：'+str(error),suggested_exclusions=[])
        updated['confirmed_local_review5r'] = summary
        return updated
