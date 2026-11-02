from flask import Flask, render_template, request, send_from_directory, jsonify, Response
from detector import ROOT, read
from runtime_paths import RESOURCE_ROOT, DATA, OUTPUTS, SETTINGS, WORK_ROOT
from model_manager import manager
from settings_api import settings_api
from reports import export_csv
from library import analyze_file, analyze_sample, select_sample, public_catalog, catalog, save_result, importer, latest_results
import uuid
import json
import re
import threading
import cv2
from datetime import datetime, timezone

app = Flask(__name__, template_folder=str(RESOURCE_ROOT/'templates'), static_folder=str(RESOURCE_ROOT/'static'))
app.register_blueprint(settings_api)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['MAX_CONTENT_LENGTH'] = 40 * 1024 * 1024
analysis_lock = threading.Lock()
review_lock = threading.Lock()
jobs_lock = threading.Lock()
jobs = {}
(ROOT/'outputs').mkdir(exist_ok=True)

@app.before_request
def request_limits():
    if request.path == '/api/settings/model':
        request.max_content_length = 512 * 1024 * 1024

@app.get('/api/health')
def health():
    from launch import workspace_identity
    return jsonify(service='xray-poc', version=5, detector_version=2, startup_protocol=2, workspace_id=workspace_identity(WORK_ROOT))

@app.get('/')
def index():
    return render_template('user.html')

@app.get('/settings')
def settings_page():
    return render_template('settings.html')

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
        result = latest_results().get(item['sha256'])
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
                filename = PathName(file.filename)
                if not filename or filename in ('.','..') or ':' in filename or filename.rsplit('.',1)[-1].lower() not in ('png','jpg','jpeg','tif','tiff'):
                    raise ValueError('無效的照片檔名')
                staging = OUTPUTS/(uuid.uuid4().hex + '.upload')
                try:
                    file.save(staging)
                    read(staging)
                    upload_dir = DATA/'uploads'/uuid.uuid4().hex[:12]
                    upload_dir.mkdir(parents=True)
                    upload = upload_dir/filename
                    staging.replace(upload)
                finally:
                    staging.unlink(missing_ok=True)
                result = analyze_sample(select_sample(upload.relative_to(DATA).as_posix()), threshold)
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
        result = json.loads(path.read_text(encoding='utf-8'))
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
        result = json.loads(path.read_text(encoding='utf-8'))
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
    path = RESOURCE_ROOT/'review'/'comparison.json'
    return jsonify(json.loads(path.read_text(encoding='utf-8'))) if path.exists() else jsonify(samples=[])

@app.get('/outputs/<path:filename>')
def output(filename):
    return send_from_directory(ROOT/'outputs', filename)

@app.errorhandler(413)
def too_large(e):
    return jsonify(error='模型檔案超過 512 MB' if request.path == '/api/settings/model' else '檔案超過 40 MB，請縮小後重試'), 413

@app.get('/api/station')
def station_status():
    return jsonify(acquisition=importer.info(), model=manager.snapshot().info())


@app.post('/api/reports/screws')
def screw_report():
    payload = request.get_json(silent=True) or {}
    ids = payload.get('sample_ids')
    if not isinstance(ids, list) or not ids or len(ids) != len(set(str(x) for x in ids)) or any(not isinstance(x,str) for x in ids):
        return jsonify(error='請選擇要匯出的照片批次'), 400
    with analysis_lock, review_lock:
        items = {item['id']:item for item in catalog() if not item['is_reference']}
        history = latest_results()
        entries, unfinished = [], []
        for sample_id in ids:
            item = items.get(sample_id)
            if item is None:
                return jsonify(error='照片清單已變更，請重新選擇批次'), 409
            result = history.get(item['sha256'])
            decision = (result or {}).get('image_review',{}).get('decision')
            if decision not in ('screw','no_screw_seen'):
                unfinished.append(item.get('display_name',item['filename']))
            else:
                entries.append((item,result))
        if unfinished:
            return jsonify(error=f'尚有 {len(unfinished)} 張未完成複判或需再確認，請先完成本批次', files=unfinished), 409
        content, count = export_csv(entries)
        report_id = uuid.uuid4().hex[:12]
        directory = ROOT/'reports'; directory.mkdir(exist_ok=True)
        (directory/f'{report_id}.csv').write_bytes(content)
        (directory/f'{report_id}.json').write_text(json.dumps(dict(
            exported_at=datetime.now(timezone.utc).isoformat(), sample_ids=ids,
            analysis_runs=[r['name'] for _,r in entries], screw_rows=count,
            station_id=SETTINGS.get('station_id','未設定')),ensure_ascii=False,indent=2),encoding='utf-8')
    return Response(content, mimetype='text/csv', headers={
        'Content-Disposition':f'attachment; filename="loose-screws-{report_id}.csv"',
        'X-Screw-Rows':str(count), 'X-Report-ID':report_id})


def start_background():
    def analyze_import(path, filename):
        with analysis_lock:
            return analyze_file(path, filename)
    importer.analyze = analyze_import
    importer.start()


if __name__ == '__main__':
    start_background()
    app.run(host='127.0.0.1', port=8765, debug=False)
