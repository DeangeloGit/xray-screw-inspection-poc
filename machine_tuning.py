"""Machine-specific tuning previews, separate from production photos and reviews."""
import json
import re
import shutil
import uuid
from pathlib import Path

from flask import jsonify, render_template, request, send_from_directory
import cv2
import numpy as np
from detector import detect, write_image, DETECTOR_VERSION
from machine_profiles import selected_profile
from runtime_paths import STATE
from station_settings import detection_threshold, save_machine_threshold, validate_threshold


def write_aligned_overlay(directory, result):
    """Draw reference-frame candidate boxes directly on the aligned image."""
    gray = cv2.imdecode(np.frombuffer((directory / 'aligned.png').read_bytes(), np.uint8), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise ValueError('無法讀取對齊後影像')
    overlay = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    height, width = gray.shape
    for candidate in result['candidates']:
        x, y, w, h = (candidate[key] for key in ('x', 'y', 'w', 'h'))
        color = (60, 65, 245) if candidate['priority'] == 'high' else (0, 185, 245)
        cv2.rectangle(overlay, (max(0, x-5), max(0, y-5)),
                      (min(width-1, x+w+5), min(height-1, y+h+5)), color, 2)
        cv2.putText(overlay, str(candidate['id']), (max(0, x-5), max(14, y-11)),
                    cv2.FONT_HERSHEY_SIMPLEX, .6, color, 2)
    write_image(str(directory / 'aligned_overlay.png'), overlay)


def register_tuning(app, analysis_lock):
    root = STATE / 'tuning-previews'

    @app.get('/engineer/machines/<machine_id>/tuning')
    def tuning_page(machine_id):
        profile = selected_profile(machine_id)
        return render_template('machine_tuning.html', machine=profile,
                               threshold=detection_threshold(machine_id))

    @app.post('/api/machines/<machine_id>/tuning/preview')
    def tuning_preview(machine_id):
        directory = None
        try:
            threshold = validate_threshold(float(request.form.get('threshold', '')))
            upload = request.files.get('image')
            if not upload or not upload.filename:
                raise ValueError('請上傳一張此機型的異常照片')
            filename = Path(upload.filename.replace('\\', '/')).name
            suffix = Path(filename).suffix.lower()
            if suffix not in ('.png', '.jpg', '.jpeg', '.tif', '.tiff'):
                raise ValueError('異常照片需為 PNG、JPEG 或 TIFF')
            with analysis_lock:
                profile = selected_profile(machine_id)
                if request.form.get('reference_sha256') != profile['reference_sha256']:
                    return jsonify(error='正常參考圖已更換，請重新整理調校頁面'), 409
                token = uuid.uuid4().hex
                directory = root / token
                directory.mkdir(parents=True)
                target = directory / ('input' + suffix)
                upload.save(target)
                result = detect(profile['reference'], target, token, threshold,
                                output_directory=directory)
                write_aligned_overlay(directory, result)
                metadata = dict(detector_version=DETECTOR_VERSION, machine_id=machine_id, reference_sha256=profile['reference_sha256'],
                                threshold=threshold, previous_threshold=detection_threshold(machine_id))
                (directory / 'preview.json').write_text(json.dumps(metadata), encoding='utf-8')
            result['tuning_asset_base'] = f'/api/machines/{machine_id}/tuning/{token}'
            return jsonify(result=result, preview_id=token, threshold=threshold, filename=filename,
                           reference_name=profile.get('reference_name', Path(profile['reference']).name),
                           count=result['proposal_count'], warning=result['alignment_warning'],
                           assets={key: f'/api/machines/{machine_id}/tuning/{token}/{key}.png'
                                   for key in ('reference', 'aligned', 'aligned_overlay', 'all_overlay', 'difference')})
        except Exception as error:
            if directory is not None:
                shutil.rmtree(directory, ignore_errors=True)
            app.logger.info('Tuning preview failed: %s', error)
            return jsonify(error='無法完成調校預覽：' + str(error)), 400

    @app.get('/api/machines/<machine_id>/tuning/<token>/<filename>')
    def tuning_asset(machine_id, token, filename):
        if not re.fullmatch('[a-f0-9]{32}', token) or not re.fullmatch(r'(?:reference|aligned|aligned_overlay|all_overlay|difference|source|overlay|crop_\d+|reference_crop_\d+|baseline_crop_\d+|baseline_ref_\d+|structure_ref_\d+|structure_target_\d+)\.png|result\.json', filename):
            return jsonify(error='找不到預覽'), 404
        metadata = root / token / 'preview.json'
        if not metadata.is_file() or json.loads(metadata.read_text())['machine_id'] != machine_id:
            return jsonify(error='找不到此機型的預覽'), 404
        return send_from_directory(root / token, filename)


    @app.get('/api/machines/<machine_id>/tuning/catalog')
    def tuning_catalog(machine_id):
        from library import public_catalog
        return jsonify(public_catalog(selected_profile(machine_id)))

    @app.post('/api/machines/<machine_id>/tuning/<token>/review')
    def tuning_review(machine_id, token):
        if not re.fullmatch('[a-f0-9]{32}', token):
            return jsonify(error='找不到調校紀錄'), 404
        metadata = root / token / 'preview.json'
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or body.get('label') not in ('screw', 'normal', 'uncertain') or type(body.get('id')) is not int:
            return jsonify(error='無效的候選註記'), 400
        with analysis_lock:
            if not metadata.is_file() or json.loads(metadata.read_text())['machine_id'] != machine_id:
                return jsonify(error='找不到此機型的調校紀錄'), 404
            path = root / token / 'result.json'
            result = json.loads(path.read_text(encoding='utf-8'))
            if body['id'] not in [c['id'] for c in result['candidates']]:
                return jsonify(error='找不到候選'), 400
            result.setdefault('human_reviews', {})[str(body['id'])] = body['label']
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(path)
        return jsonify(saved=True)

    @app.post('/api/machines/<machine_id>/tuning/apply')
    def tuning_apply(machine_id):
        body = request.get_json(silent=True)
        token = body.get('preview_id') if isinstance(body, dict) else None
        if not isinstance(token, str) or not re.fullmatch('[a-f0-9]{32}', token):
            return jsonify(error='請先上傳異常照片並完成調校預覽'), 400
        path = root / token / 'preview.json'
        if not path.is_file():
            return jsonify(error='調校預覽不存在，請重新試算'), 400
        with analysis_lock:
            metadata = json.loads(path.read_text(encoding='utf-8'))
            profile = selected_profile(machine_id)
            if metadata.get('detector_version') != DETECTOR_VERSION:
                return jsonify(error='偵測版本已更新，請重新試算後再套用'), 409
            if metadata['machine_id'] != machine_id or metadata['reference_sha256'] != profile['reference_sha256']:
                return jsonify(error='機型或正常參考圖已變更，請重新試算'), 409
            if detection_threshold(machine_id) != metadata['previous_threshold']:
                return jsonify(error='此機型的敏感度已被更新，請重新試算再套用'), 409
            save_machine_threshold(machine_id, metadata['threshold'])
        return jsonify(saved=True, machine_id=machine_id, threshold=metadata['threshold'])
