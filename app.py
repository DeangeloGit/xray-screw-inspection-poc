from flask import Flask, render_template, request, send_from_directory, jsonify, Response
from detector import ROOT, read, DETECTOR_VERSION
from runtime_paths import RESOURCE_ROOT, DATA, OUTPUTS, SETTINGS, WORK_ROOT
from model_manager import manager
from settings_api import settings_api
from station_settings import source_scope, detection_threshold, validate_threshold, update_settings
from machine_profiles import public_profiles, selected_profile, save_profile, select_profile, profiles, matches
from reports import export_csv, report_rows
from review_workflow import effective_review, summarize_positions
from library import analyze_file, analyze_sample, select_sample, public_catalog, catalog, save_result, importer, latest_results, analysis_failures
import uuid
import hashlib
from functools import lru_cache
import json
import re
import threading
import cv2
from datetime import datetime, timezone

app = Flask(__name__, template_folder=str(RESOURCE_ROOT/'templates'), static_folder=str(RESOURCE_ROOT/'static'))
app.register_blueprint(settings_api)
from dino_examples import dino_examples
app.register_blueprint(dino_examples)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['MAX_CONTENT_LENGTH'] = 40 * 1024 * 1024
analysis_lock = threading.Lock()
review_lock = threading.Lock()
jobs_lock = threading.Lock()
jobs = {}
from machine_tuning import register_tuning
register_tuning(app, analysis_lock)
(ROOT/'outputs').mkdir(exist_ok=True)

@app.before_request
def request_limits():
    if request.path == '/api/settings/model':
        request.max_content_length = 512 * 1024 * 1024

def require_machine_context():
    threshold_token = request.headers.get('X-Inspection-Threshold')
    if threshold_token is not None and float(threshold_token) != detection_threshold():
        raise ValueError('此機型敏感度已變更，請更新照片清單後重新檢查')
    source_token = request.headers.get('X-Inspection-Source')
    if source_token and source_token != source_scope()['id']:
        raise ValueError('取圖資料夾已變更，請更新照片清單後重試')
    token = request.headers.get('X-Inspection-Machine')
    if token:
        profile = selected_profile()
        if token != profile['id'] + ':' + profile['reference_sha256']:
            raise ValueError('本站檢測機型或參考圖已變更，請重新整理頁面')

@app.get('/api/settings/detection')
def get_detection_settings():
    return jsonify(threshold=detection_threshold())


@app.post('/api/settings/detection')
def set_detection_settings():
    return jsonify(error='請從機型旁的調校按鈕進入，預覽後套用至該機型'), 409


@app.get('/api/health')
def health():
    from launch import workspace_identity
    from detection_runtime import PIPELINE
    return jsonify(service='xray-poc', version=5, detector_version=DETECTOR_VERSION, pipeline=PIPELINE, startup_protocol=2, workspace_id=workspace_identity(WORK_ROOT))

@app.get('/')
def index():
    return render_template('user.html')

@app.get('/settings')
def settings_page():
    return render_template('engineer.html', initial_tab='source')

@app.get('/engineer')
def engineer():
    return render_template('engineer.html')

@app.get('/help/<mode>')
def manual(mode):
    if mode not in ('user', 'engineer'):
        return jsonify(error='找不到這份使用說明'), 404
    return render_template('help.html', mode=mode)

@app.get('/api/machines')
def machines():
    return jsonify(public_profiles())

@app.post('/api/machines')
def machine_save():
    try:
        with analysis_lock:
            item = save_profile(request.form.get('name'), request.files.get('reference'), request.form.get('id') or None)
        return jsonify(saved=True, machine_id=item['id'], **public_profiles())
    except (ValueError, OSError, cv2.error) as e:
        return jsonify(error=str(e)), 400

@app.post('/api/machines/select')
def machine_select():
    try:
        if not (request.get_json(silent=True) or {}).get('id'):
            raise ValueError('請指定檢測機型')
        with analysis_lock:
            profile = select_profile((request.get_json(silent=True) or {}).get('id'))
        return jsonify(machine=profile, **public_profiles())
    except (ValueError, OSError) as e:
        return jsonify(error=str(e)), 400

@app.post('/api/inspection/context')
def inspection_context():
    from settings_api import absolute_folder, validate_source
    from station_settings import acquisition_config, update_settings, LOCK
    body = request.get_json(silent=True) or {}
    try:
        if not isinstance(body, dict) or not isinstance(body.get('id'), str) or not body['id'] or type(body.get('enabled')) is not bool:
            raise ValueError('請指定檢測機型與取圖設定')
        with analysis_lock, LOCK:
            profile = selected_profile(body['id'])
            value = body.get('source', '')
            if not isinstance(value, str):
                raise ValueError('請指定完整取圖路徑')
            source = ''
            if value.strip() or body['enabled']:
                path = absolute_folder(value)
                validate_source(path)
                source = str(path)
            config = dict(acquisition_config(), source=source, enabled=body['enabled'])
            update_settings(selected_machine=profile['id'], acquisition=config)
        return jsonify(saved=True, machine=profile, source=source_scope(config))
    except (ValueError, OSError) as error:
        return jsonify(error=str(error)), 400

@lru_cache(maxsize=32)
def reference_thumbnail(path, modified, size):
    image = read(path)
    h, w = image.shape
    image = cv2.resize(image, (max(1, round(w*160/max(h,w))), max(1, round(h*160/max(h,w)))))
    ok, encoded = cv2.imencode('.png', (image*255).astype('uint8'))
    if not ok:
        raise ValueError('參考圖預覽失敗')
    return encoded.tobytes()

@app.get('/api/machines/<machine_id>/reference')
def machine_reference(machine_id):
    for item in profiles():
        if item['id'] == machine_id:
            from pathlib import Path
            path = Path(item['reference'])
            if request.args.get('preview') == '1' and path.is_file():
                stat = path.stat()
                response = Response(reference_thumbnail(str(path), stat.st_mtime_ns, stat.st_size), mimetype='image/png')
                response.cache_control.no_cache = True
                return response
            return send_from_directory(path.parent, path.name)
    return jsonify(error='找不到機型'), 404

@app.errorhandler(ValueError)
def invalid_input(error):
    return jsonify(error=str(error)), 400

@app.get('/api/samples')
def samples():
    return jsonify(public_catalog())

@app.get('/api/samples/<sample_id>/result')
def sample_result(sample_id):
    try:
        item = select_sample(sample_id)
        result = latest_results().get(item['sha256'])
        return jsonify(dict(result, image_review=effective_review(result))) if result else (jsonify(error='此照片尚未檢查'), 404)
    except ValueError as e:
        return jsonify(error=str(e)), 404

@app.post('/api/analyze')
def analyze():
    try:
        threshold = float(request.form['threshold']) if 'threshold' in request.form else None
        if threshold is not None and not .03 <= threshold <= .4:
            raise ValueError('門檻需介於 0.03 與 0.40')
        sample = request.form.get('sample', 'ng_5')
        with analysis_lock:
            require_machine_context()
            if threshold is not None and threshold != detection_threshold():
                raise ValueError('請先儲存此機型敏感度，並重新整理頁面後檢查')
            if 'image' in request.files and request.files['image'].filename:
                file = request.files['image']
                filename = PathName(file.filename)
                if not filename or filename in ('.','..') or ':' in filename or filename.rsplit('.',1)[-1].lower() not in ('png','jpg','jpeg','tif','tiff'):
                    raise ValueError('無效的照片檔名')
                staging = OUTPUTS/(uuid.uuid4().hex + '.upload')
                try:
                    file.save(staging)
                    read(staging)
                    upload_dir = DATA/'uploads'/source_scope()['id']/uuid.uuid4().hex[:12]
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
    with analysis_lock, review_lock:
        require_machine_context()
        result = json.loads(path.read_text(encoding='utf-8'))
        if result.get('version') != DETECTOR_VERSION:
            return jsonify(error='偵測版本已更新，請重新檢查此照片'), 409
        if result.get('threshold', .13) != detection_threshold():
            return jsonify(error='此機型敏感度已變更，請重新檢查此照片'), 409
        if not matches(result, selected_profile()):
            return jsonify(error='此紀錄不屬於目前機型／參考圖，請重新檢查'), 409
        if candidate_id not in [c['id'] for c in result['candidates']]:
            return jsonify(error='未知候選'), 400
        result.setdefault('human_reviews', {})[str(candidate_id)] = label
        summarize_positions(result, datetime.now(timezone.utc).isoformat())
        save_result(result)
    return jsonify(saved=True, id=candidate_id, label=label, image_review=result.get('image_review'))

@app.post('/api/image-review/<name>')
def image_review(name):
    path = result_path(name)
    if path is None:
        return jsonify(error='未知分析紀錄'), 404
    payload = request.get_json(silent=True) or {}
    decision = payload.get('decision')
    if decision not in ('screw', 'no_screw_seen', 'uncertain'):
        return jsonify(error='無效的整張照片複核結果'), 400
    with analysis_lock, review_lock:
        require_machine_context()
        result = json.loads(path.read_text(encoding='utf-8'))
        if result.get('version') != DETECTOR_VERSION:
            return jsonify(error='偵測版本已更新，請重新檢查此照片'), 409
        if result.get('threshold', .13) != detection_threshold():
            return jsonify(error='此機型敏感度已變更，請重新檢查此照片'), 409
        if not matches(result, selected_profile()):
            return jsonify(error='此紀錄不屬於目前機型／參考圖，請重新檢查'), 409
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
    with analysis_lock:
        require_machine_context()
        profile = selected_profile()
        scope = source_scope()
    with jobs_lock:
        for job_id, job in jobs.items():
            if job['state'] == 'running':
                if (job.get('source',{}).get('id') != scope['id'] or
                        job.get('machine',{}).get('id') != profile['id'] or
                        job.get('machine',{}).get('reference_sha256') != profile['reference_sha256']):
                    return jsonify(error='其他機型或來源的批次正在完成，請稍後再檢查目前批次'), 409
                return jsonify(id=job_id, **job), 202
        job_id = uuid.uuid4().hex[:12]
        items = [s for s in catalog(scope) if not s['is_reference']]
        jobs[job_id] = dict(source=scope, machine=profile, state='running', total=len(items), completed=0, errors=[], current=None)
    def work():
        for item in items:
            with jobs_lock:
                jobs[job_id]['current'] = item['filename']
            try:
                with analysis_lock:
                    analyze_sample(item, profile=profile)
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
    from detection_runtime import PIPELINE
    return jsonify(acquisition=importer.info(), model=manager.snapshot().info(), pipeline=PIPELINE)


@app.post('/api/reports/screws/preview')
@app.post('/api/reports/screws')
def screw_report():
    payload = request.get_json(silent=True) or {}
    ids = payload.get('sample_ids')
    if not isinstance(ids, list) or not ids or len(ids) != len(set(str(x) for x in ids)) or any(not isinstance(x,str) for x in ids):
        return jsonify(error='請選擇要匯出的照片批次'), 400
    with analysis_lock, review_lock:
        require_machine_context()
        items = {item['id']:item for item in catalog() if not item['is_reference']}
        history = latest_results()
        profile = selected_profile()
        failures = analysis_failures(profile)
        entries, unfinished = [], []
        for sample_id in ids:
            item = items.get(sample_id)
            if item is None:
                return jsonify(error='照片清單已變更，請重新選擇批次'), 409
            result = history.get(item['sha256'])
            if result:
                result = dict(result, image_review=effective_review(result))
            decision = (result or {}).get('image_review',{}).get('decision')
            if decision not in ('screw','no_screw_seen'):
                result = dict(result or {}, machine=(result or {}).get('machine',profile))
                failure = failures.get(item['sha256']) if not result.get('name') else None
                if failure:
                    issue = dict(status='無法分析', reason=failure['error'])
                elif decision == 'uncertain':
                    issue = dict(status='需再確認', reason='人工判定仍有不確定位置或照片需再確認')
                elif result.get('name'):
                    remaining = sum(str(c['id']) not in result.get('human_reviews',{}) for c in result.get('candidates',[]))
                    issue = dict(status='未完成複判', reason=f'尚有 {remaining} 個標記位置未判定' if remaining else '尚待人工檢查照片')
                else:
                    issue = dict(status='尚未檢查', reason='尚未完成分析或人工複判')
                result['report_issue'] = issue
                unfinished.append(dict(sample_id=sample_id, filename=item.get('display_name',item['filename']), **issue))
            entries.append((item,result))
        rows = report_rows(entries)
        screw_rows = sum(row['kind']=='螺絲結果' for row in rows)
        unresolved_rows = sum(row['kind']=='待處理異常' for row in rows)
        signature = hashlib.sha256(json.dumps(dict(ids=ids,rows=rows,
            reviews=[r.get('image_review',{}) for _,r in entries]),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        if request.path.endswith('/preview'):
            return jsonify(rows=rows, photo_count=len(entries), completed_count=len(entries)-len(unfinished),
                           screw_rows=screw_rows, unresolved_count=len(unfinished), unresolved_rows=unresolved_rows,
                           machine=profile['name'], preview_token=signature)
        if payload.get('preview_token') and payload['preview_token'] != signature:
            return jsonify(error='複判結果已更新，請重新預覽再匯出'), 409
        content, count = export_csv(entries)
        report_id = uuid.uuid4().hex[:12]
        directory = ROOT/'reports'; directory.mkdir(exist_ok=True)
        (directory/f'{report_id}.csv').write_bytes(content)
        (directory/f'{report_id}.json').write_text(json.dumps(dict(
            exported_at=datetime.now(timezone.utc).isoformat(), sample_ids=ids,
            analysis_runs=[r['name'] for _,r in entries if r.get('name')], screw_rows=count,
            unresolved=unfinished, unresolved_rows=unresolved_rows, completed_count=len(entries)-len(unfinished),
            station_id=SETTINGS.get('station_id','未設定')),ensure_ascii=False,indent=2),encoding='utf-8')
    return Response(content, mimetype='text/csv', headers={
        'Content-Disposition':f'attachment; filename="loose-screws-{report_id}.csv"',
        'X-Screw-Rows':str(count), 'X-Unresolved-Rows':str(unresolved_rows), 'X-Report-ID':report_id})


def start_background():
    # Warm only the selected reference and model, never reanalyse old photos.
    from detection_runtime import prepare_reference
    from detector import structure_mask, machine_mask
    try:
        profile=selected_profile()
        prepare_reference(profile['reference'],read,structure_mask,machine_mask)
        manager.snapshot()
    except (ValueError,OSError):
        pass  # Existing UI reports missing/unconfigured references normally.
    def analyze_import(path, filename):
        with analysis_lock:
            return analyze_file(path, filename)
    importer.analyze = analyze_import
    importer.start()


if __name__ == '__main__':
    start_background()
    app.run(host='127.0.0.1', port=8765, debug=False)
