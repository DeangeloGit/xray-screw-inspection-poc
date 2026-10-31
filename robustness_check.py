"""One synthetic perturbation check, NOT an independent accuracy evaluation."""
import cv2
import numpy as np
import json
from detector import detect, ROOT
from verify import iou

im = cv2.imread(str(ROOT/'data/ng_5.png'), cv2.IMREAD_UNCHANGED)
h, w = im.shape
# Translate, turn 90 degrees, and reduce intensity, preserving the known screw.
trans = np.float32([[1, 0, 24], [0, 1, -16]])
image = cv2.warpAffine(im, trans, (w, h), borderValue=int(np.median(im[:200, :200])))
image = (np.rot90(image).copy().astype('float32') * .9).astype('uint16')
path = ROOT/'outputs/perturbed_5.png'
cv2.imwrite(str(path), image)
result = detect(ROOT/'data/ok_0.png', path, 'perturbed_5')
label = json.loads((ROOT/'review/annotations.json').read_text())['samples']['ng_5']['objects'][0]['bbox']
x0, y0, x1, y1 = label
# Known generation geometry, independent of registration output.
x0, x1, y0, y1 = x0+24, x1+24, y0-16, y1-16
expected = [y0, w-1-x1, y1, w-1-x0]
hits = [c['id'] for c in result['candidates']
        if c['priority'] == 'high' and iou(c['source_bbox'], expected) > .15]
assert hits, 'Known screw did not survive perturbation as high-priority candidate'
report = dict(check='synthetic translation +24/-16px, 90deg rotation, intensity x0.9',
              source='data/ng_5.png', expected_bbox=expected, high_hit_ids=hits,
              candidates=result['proposal_count'], high_count=result['high_count'],
              limitation='Same supplied image transformed; does not measure generalization or detection accuracy.')
(ROOT/'review/robustness.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
print(report)
