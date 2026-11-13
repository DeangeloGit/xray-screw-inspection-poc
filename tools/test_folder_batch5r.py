"""Synthetic workflow tests; never claims real DINO acceptance."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import Flask
from PIL import Image
from folder_batch5r import discover, register, sha, summarize, verify_report


class FolderBatchTests(unittest.TestCase):
    def test_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            golden = root/'golden.png'; Image.new('RGB', (160, 160), 'white').save(golden)
            profile = dict(id='test', name='KPH33', reference=str(golden), reference_sha256=sha(golden))
            snapshot = SimpleNamespace(error=None, session=object(), info=lambda: {'fingerprint': 'synthetic'})
            def detect(ref, target, name, threshold, model_snapshot, output_directory):
                with Image.open(target) as im:
                    pixel = im.convert('RGB').getpixel((0, 0))[0]
                for filename in ('reference.png', 'aligned.png'):
                    Image.new('RGB', (160, 160), 'white').save(output_directory/filename)
                candidate = dict(id=1, x=20, y=20, w=10, h=10)
                keep = [candidate] if pixel == 0 else []
                removed = [] if keep or pixel == 255 else [candidate]
                result = dict(candidates=keep, filtered_candidates=removed,
                              pre_ai_count=len(keep)+len(removed), alignment_warning=False)
                (output_directory/'result.json').write_text(json.dumps(result), encoding='utf-8')
                return result
            app = Flask(__name__)
            register(app, root/'jobs', threading.Lock(), threading.RLock(), detect,
                     lambda: snapshot, lambda _: profile, lambda _: .13)
            client = app.test_client()
            self.assertEqual(client.post('/api/5r/batches', json={'folder': str(root)}).status_code, 400)
            for label in ('NG', 'OK'):
                folder = root/label; (folder/'nested').mkdir(parents=True)
                Image.new('RGB', (160, 160), 'black').save(folder/'alarm.png')
                Image.new('RGB', (160, 160), 'gray').save(folder/'nested/no-alarm.PNG')
                Image.new('RGB', (160, 160), 'gray').save(folder/'duplicate.png')
                golden_copy = folder/'self.png'; golden_copy.write_bytes(golden.read_bytes())
                (folder/'broken.jpg').write_text('invalid image')
                self.assertEqual(len(discover(folder)[2]), 5)
                response = client.post('/api/5r/batches', json={'folder': str(folder), 'machine_id': 'test'})
                self.assertEqual(response.status_code, 202)
                token = response.json['id']
                deadline = time.monotonic()+15
                while time.monotonic() < deadline:
                    job = client.get('/api/5r/batches/'+token).json
                    if job['state'] not in ('running', 'reporting'): break
                    time.sleep(.02)
                self.assertEqual(job['state'], 'done', job)
                self.assertEqual(job['summary']['errors'], 1)
                self.assertEqual(job['summary']['reference_self'], 1)
                self.assertEqual(job['summary']['completed'], 3)
                self.assertEqual(job['summary']['ng_missed'], 2 if label == 'NG' else 0)
                self.assertEqual(job['summary']['ok_false_alarm'], 1 if label == 'OK' else 0)
                directory = root/'jobs'/token
                check = json.loads((directory/'verification.json').read_text())
                self.assertEqual(check['candidates'], 3)
                with client.get(job['report']) as response:
                    self.assertEqual(response.status_code, 200)
                self.assertEqual(client.get(f'/5r/batches/{token}/../../golden.png').status_code, 404)
                (directory/'images/000000-1.jpg').unlink()
                with self.assertRaises(ValueError): verify_report(directory, check)

    def test_empty_and_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)/'[NG]'; folder.mkdir()
            with self.assertRaises(ValueError): discover(folder)
        self.assertEqual(summarize([])['total'], 0)


if __name__ == '__main__':
    unittest.main()
