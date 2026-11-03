"""Replay all frozen candidate crops through the production pair path, no redetection."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
REPORT = ROOT / 'workspace/windows-check/diagnostics/dino-47-paired-full-20261103'
BASE = REPORT.parent / 'dino-full-evaluation-20261103'


def main():
    with tempfile.TemporaryDirectory(prefix='paired-runtime-check-') as tmp:
        tmp = Path(tmp)
        config = tmp / 'station.json'
        config.write_text(json.dumps(dict(workspace=str(tmp / 'work'), model_root=str(ROOT / 'models'), allow_cpu_fallback=True)))
        os.environ['XRAY_CONFIG'] = str(config)
        os.environ['XRAY_WORKSPACE'] = str(tmp / 'work')
        from model_manager import ModelManager
        from detector import classify_dino_candidate
        from dino_adapter import input_image, PAIRED_POLICY
        paired = ModelManager(allow_cpu=True).snapshot('dino-paired-47-20261103')
        original = ModelManager(allow_cpu=True).snapshot('dino-examples-176c7281352c4e74')
        assert not paired.error and not original.error
        assert paired.identity != original.identity
        assert paired.manifest['example_bank'] == original.manifest['example_bank']
        cases = json.loads((REPORT / 'cases.json').read_text(encoding='utf-8'))
        vectors = np.load(REPORT / 'features.npz')
        count = {'OK': 0, 'NG': 0}; seen = set(); actual_inputs = 0
        def saved_embedding(m, session, crop):
            nonlocal actual_inputs
            pixels = np.asarray(input_image(m, crop))[:, :, 0].copy()
            key = hashlib.sha256(pixels.tobytes()).hexdigest()
            assert key in vectors, 'Production crop differs from report input: ' + key
            seen.add(key); actual_inputs += 1
            return vectors[key]
        images = {}
        selected = []
        with patch('dino_adapter.embedding', side_effect=saved_embedding):
            for z in cases:
                if z['sha'] not in images:
                    folder = BASE / 'photos' / z['sha']
                    images.clear()
                    images[z['sha']] = [np.asarray(Image.open(folder / name).convert('L'), np.float32)/255
                                        for name in ['aligned.png', 'reference.png']]
                target, reference = images[z['sha']]
                p = classify_dino_candidate(paired, target, reference, z['c'])
                assert p['status'] == 'active' and p['decision_policy'] == PAIRED_POLICY, p
                keep = p['action'] != 'discard'
                assert keep == z['paired_keep'], z['key']
                for side in ['target', 'reference']:
                    assert abs(p['paired_evidence'][side]['screw_margin'] - z[side]['margin']) < 1e-6
                count[z['label']] += keep
                if ((Path(z['name']).name == '1.png' and z['id'] == 7) or
                    (Path(z['name']).name == '5.png' and z['id'] == 2) or
                    (Path(z['name']).name == '9.png' and z['id'] == 1) or
                    (z['name'].endswith('17_13_17_96.tiff') and z['id'] == 80)):
                    selected.append((z, target.copy(), reference.copy()))
        assert count == {'OK': 0, 'NG': 386}, count
        real = []
        for z, target, reference in selected:
            p = classify_dino_candidate(paired, target, reference, z['c'])
            assert p['status'] == 'active' and (p['action'] != 'discard') == z['paired_keep'], z['key']
            for side in ['target', 'reference']:
                assert abs(p['paired_evidence'][side]['screw_margin'] - z[side]['margin']) < 1e-5
            real.append(z['key'])
        assert len(real) == 4
        missing = paired.classify(np.zeros((50,50), np.float32))
        assert missing['status'] == 'error' and missing['action'] != 'discard'
        result = dict(success=True, candidates=len(cases), kept=count, actual_preprocessed_inputs=actual_inputs,
                      unique_input_hashes=len(seen), real_inference_cases=real, fingerprint=paired.identity,
                      validation='Production detector crop + snapshot + pair decision; cached embeddings for all candidates; actual ONNX for 4 cases; no difference rerun')
        out = ROOT / 'workspace/dino-paired-release-20261103'
        out.mkdir(exist_ok=True)
        (out / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
