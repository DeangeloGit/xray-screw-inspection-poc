from flask import Flask, render_template, request, send_from_directory, jsonify
from detector import ROOT
from library import analyze_file, analyze_sample, select_sample, public_catalog, catalog, save_result
import uuid
import json
import re
import threading
import cv2
from datetime import datetime, timezone

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['MAX_CONTENT_LENGTH'] = 40 * 1024 * 1024
analysis_lock = threading.Lock()
review_lock = threading.Lock()
jobs_lock = threading.Lock()
jobs = {}
(ROOT/'outputs').mkdir(exist_ok=True)

@app.get('/api/health')
def health():
    return jsonify(service='xray-poc', version=3, detector_version=2)

@app.get('/')
def index():
    return render_template('user.html')

@app.get('/engineer')
def engineer():
    return render_template('engineer.html')

@app.get('/help/<mode>')
def manual(mode):
    if mode not in ('user', 'engineer'):
        return jsonify(error='找不到這份使用說明'), 404
    return render_template('help.html', mode=mode)

@app.get('/api/samples')
def samples():
    return jsonify(public_catalog())

@app.get('/api/samples/<sample_id>/result')
def sample_result(sample_id):
    try:
        item = select_sample(sample_id)
        from library import cached_result
        result = cached_result(item)
        return jsonify(result) if result else (jsonify(error='此照片尚未檢查'), 404)
    except ValueError as e:
        return jsonify(error=str(e)), 404

@app.post('/api/analyze')
def analyze():
    try:
        threshold = float(request.form.get('threshold', .13))
        if not .03 <= threshold <= .4:
            raise ValueError('門檻需介於 0.03 與 0.40')
        sample = request.form.get('sample', 'ng_5')
        with analysis_lock:
            if 'image' in request.files and request.files['image'].filename:
                file = request.files['image']
                upload = ROOT/'outputs'/f'{uuid.uuid4().hex[:12]}_upload.png'
                file.save(upload)
                result = analyze_file(upload, PathName(file.filename), threshold)
            else:
                result = analyze_sample(select_sample(sample), threshold)
        return jsonify(result)
    except cv2.error:
        return jsonify(error='影像處理失敗，請確認檔案格式與拍攝內容'), 400
    except (ValueError, TypeError) as e:
        return jsonify(error=str(e)), 400


def PathName(value):
    return value.replace('\\', '/').split('/')[-1]


def result_path(name):
    if not re.fullmatch(r'[a-f0-9]{12}', name):
        return None
    path = ROOT/'outputs'/name/'result.json'
    return path if path.is_file() else None

@app.post('/api/review/<name>')
def review(name):
    path = result_path(name)
    if path is None:
        return jsonify(error='未知分析紀錄'), 404
    payload = request.get_json(silent=True) or {}
    label = payload.get('label')
    candidate_id = payload.get('id')
    if label not in ('screw', 'normal', 'uncertain') or type(candidate_id) is not int:
        return jsonify(error='無效的複核結果'), 400
    with review_lock:
        result = json.loads(path.read_text())
        if candidate_id not in [c['id'] for c in result['candidates']]:
            return jsonify(error='未知候選'), 400
        result.setdefault('human_reviews', {})[str(candidate_id)] = label
        # Candidate edits invalidate prior whole-photo completion.
        result.pop('image_review', None)
        save_result(result)
    return jsonify(saved=True, id=candidate_id, label=label)

@app.post('/api/image-review/<name>')
def image_review(name):
    path = result_path(name)
    if path is None:
        return jsonify(error='未知分析紀錄'), 404
    payload = request.get_json(silent=True) or {}
    decision = payload.get('decision')
    if decision not in ('screw', 'no_screw_seen', 'uncertain'):
        return jsonify(error='無效的整張照片複核結果'), 400
    with review_lock:
        result = json.loads(path.read_text())
        labels = result.get('human_reviews', {})
        if len(labels) < len(result['candidates']):
            return jsonify(error='請先逐一確認所有疑似位置'), 400
        if decision == 'no_screw_seen' and any(v != 'normal' for v in labels.values()):
            return jsonify(error='仍有螺絲或不確定的位置，不能標記未見螺絲'), 400
        result['image_review'] = dict(decision=decision, by='operator',
                                      at=datetime.now(timezone.utc).isoformat())
        save_result(result)
    return jsonify(saved=True, image_review=result['image_review'])

@app.post('/api/batch')
def batch():
    with jobs_lock:
        for job_id, job in jobs.items():
            if job['state'] == 'running':
                return jsonify(id=job_id, **job), 202
        job_id = uuid.uuid4().hex[:12]
        items = [s for s in catalog() if not s['is_reference']]
        jobs[job_id] = dict(state='running', total=len(items), completed=0, errors=[], current=None)
    def work():
        for item in items:
            with jobs_lock:
                jobs[job_id]['current'] = item['filename']
            try:
                with analysis_lock:
                    analyze_sample(item)
            except (ValueError, cv2.error, OSError) as e:
                with jobs_lock:
                    jobs[job_id]['errors'].append(dict(file=item['filename'], message=str(e)))
            except Exception:
                with jobs_lock:
                    jobs[job_id]['errors'].append(dict(file=item['filename'], message='處理失敗，請個別檢查'))
            finally:
                with jobs_lock:
                    jobs[job_id]['completed'] += 1
        with jobs_lock:
            jobs[job_id]['state'] = 'done'
            jobs[job_id]['current'] = None
    threading.Thread(target=work, daemon=True).start()
    return jsonify(id=job_id, **jobs[job_id]), 202

@app.get('/api/batch/<job_id>')
def batch_status(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        return jsonify(id=job_id, **job) if job else (jsonify(error='找不到批次工作'), 404)

@app.get('/api/benchmark')
def benchmark():
    path = ROOT/'review'/'comparison.json'
    return jsonify(json.loads(path.read_text())) if path.exists() else jsonify(samples=[])

@app.get('/outputs/<path:filename>')
def output(filename):
    return send_from_directory(ROOT/'outputs', filename)

@app.errorhandler(413)
def too_large(e):
    return jsonify(error='檔案超過 40 MB，請縮小後重試'), 413

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8765, debug=False)
