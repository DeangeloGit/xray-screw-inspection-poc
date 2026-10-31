"""Regression checks use provisional visual labels, never detector inputs."""
import json
import shutil
from pathlib import Path
import io
import cv2
import numpy as np
from detector import ROOT, detect, source_points
from app import app


def iou(a, b):
    left, top = max(a[0], b[0]), max(a[1], b[1])
    right, bottom = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, right-left)*max(0, bottom-top)
    union = (a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-inter
    return inter/max(union, 1)


def run():
    uploads_before = set((ROOT/'data/uploads').glob('*'))
    annotations = json.loads((ROOT/'review/annotations.json').read_text())
    rows = []
    for name in ['ok_0', 'ng_5', 'ng_9']:
        result = detect(ROOT/'data/ok_0.png', ROOT/f'data/{name}.png', name+'_v2')
        known = annotations['samples'].get(name, {}).get('objects', [])
        high_hits = 0
        for obj in known:
            matched = [c for c in result['candidates'] if iou(c['source_bbox'], obj['bbox']) > .15]
            assert matched, f'{name}: visible screw missing from all proposals'
            assert any(c['priority'] == 'high' for c in matched), f'{name}: known screw demoted'
            high_hits += 1
        if name == 'ok_0':
            assert result['proposal_count'] == result['high_count'] == 0
        else:
            baseline = json.loads((ROOT/f'review/{name}_v1.json').read_text())
            assert result['baseline_count'] == len(baseline['candidates'])
            assert result['proposal_count'] < result['baseline_count']
            assert result['high_count'] < result['proposal_count']
        assert len(result['baseline_candidates']) == result['baseline_count']
        assert result['high_count']+result['review_count'] == result['proposal_count']
        for c in result['candidates']:
            assert (ROOT/f'outputs/{result["name"]}/crop_{c["id"]}.png').is_file()
        rows.append(dict(sample=name, v1_count=result['baseline_count'],
                         v2_count=result['proposal_count'], high_count=result['high_count'],
                         review_count=result['review_count'], known_screws=len(known),
                         high_hits=high_hits, output=f'outputs/{name}_v2/result.json'))
        print(rows[-1])
    # Native coordinate inverse mapping for all four orientations at non-square dimensions.
    raw = np.zeros((300, 400), np.uint8)
    raw[111, 222] = 1
    for k in range(4):
        yy, xx = np.where(np.rot90(raw, k))
        reg = dict(matrix=np.eye(2, 3), target_scale=1., rotation=k)
        native = source_points([[int(xx[0]), int(yy[0])]], reg, np.zeros((400, 400, 2), np.float32), raw.shape)
        assert np.allclose(native, [[222, 111]])
    with app.test_client() as client:
        assert client.get('/').status_code == 200
        for data in [{'sample': 'invalid'}, {'threshold': 'nan'}, {'threshold': '0'}, {'threshold': 'abc'}]:
            assert client.post('/api/analyze', data=data).status_code == 400
        response = client.post('/api/analyze', data={'sample': 'ok_0'})
        assert response.status_code == 200
        assert response.json['proposal_count'] == 0
        assert client.get(f'/outputs/{response.json["name"]}/source.png').status_code == 200
        assert client.get('/outputs/../../app.py').status_code == 404
        # Real uploaded PNG using rotated normal reference; no sample-name shortcut.
        im = cv2.imread(str(ROOT/'data/ok_0.png'), cv2.IMREAD_UNCHANGED)
        ok, blob = cv2.imencode('.png', np.rot90(im).copy())
        assert ok
        upload = client.post('/api/analyze', data={'image': (io.BytesIO(blob.tobytes()), 'rotated.png')})
        assert upload.status_code == 200, upload.json
        assert upload.json['rotation_ccw'] == 270
        assert upload.json['proposal_count'] == 0
        # Blank image must fail, never report OK.
        ok, blob = cv2.imencode('.png', np.zeros((256, 256), np.uint16))
        blank = client.post('/api/analyze', data={'image': (io.BytesIO(blob.tobytes()), 'blank.png')})
        assert blank.status_code == 400
        # Persistence of human confirmation is part of the delivered workflow.
        response = client.post('/api/analyze', data={'sample': 'ng_5'})
        assert response.status_code == 200
        name = response.json['name']
        preserved = (ROOT/f'outputs/{name}/result.json').read_text()
        assert client.post(f'/api/review/{name}', json={'id': 1, 'label': 'uncertain'}).status_code == 200
        saved = client.get(f'/outputs/{name}/result.json').json
        assert saved['human_reviews']['1'] == 'uncertain'
        assert client.post(f'/api/review/{name}', json={'id': 9999, 'label': 'screw'}).status_code == 400
        assert client.post(f'/api/review/{name}', json={'id': 1, 'label': 'invalid'}).status_code == 400
        assert client.post('/api/review/invalid', json={}).status_code == 404
        (ROOT/f'outputs/{name}/result.json').write_text(preserved)
    report = dict(samples=rows, threshold=.13,
                  label_status='provisional visual labels; only two known visible screws, not an exhaustive inventory',
                  checks=['known visible screw retained in both high-priority lists',
                          'self comparison zero proposals', 'native coordinate mapping four rotations',
                          'uploaded 90-degree rotated normal image', 'invalid and blank input rejection',
                          'review persistence and result download', 'baseline audit preserved'])
    (ROOT/'review/comparison.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    for generated in set((ROOT/'data/uploads').glob('*')) - uploads_before:
        shutil.rmtree(generated)
    print('PASS: regression, original coordinate mapping, upload, rejection, review persistence')

if __name__ == '__main__':
    run()
