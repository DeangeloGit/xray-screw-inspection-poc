"""RD comparison of an uploaded image pair in an isolated run directory."""
from collections import defaultdict
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

import cv2
from flask import abort, render_template, request, send_from_directory, url_for

import engineering_trace as trace

SUFFIXES = {'.png', '.jpg', '.jpeg', '.tif', '.tiff'}
STEPS = (
    ('讀入參照和待測圖', '這兩張圖是本次比較的基準。', ('reference.png', 'source.png')),
    ('解碼成灰階', '把待測照片轉成同一套灰階值，後面才比得出明暗。', ('trace-decoded.png',)),
    ('找機體和可供對位的結構', '先圈出要比較的機體，並找出可用來對位的部分。', ('trace-machine.png', 'trace-structure.png')),
    ('先對齊整張圖', '先把大方向和整體位置擺正。', ('trace-decoded.png', 'trace-global.png')),
    ('檢查拍攝範圍', '確認機體有被拍完整，避免把缺角當成異常。', ('trace-valid.png', 'trace-effective-mask.png')),
    ('保存局部修正前的比較框', '留下初步差異，方便回查哪些框在微調後消失。', ('baseline_ref_1.png', 'baseline_crop_1.png')),
    ('估計局部位移', '各區只採用有助於對齊的小幅位移。亮處表示移動較多。', ('trace-flow.png',)),
    ('微調局部位置', '讓附近邊緣更吻合，避免位置偏差造成假警報。', ('trace-global.png', 'aligned.png')),
    ('交接對齊雙圖', '兩張圖使用同一組工作座標。', ('reference.png', 'aligned.png')),
    ('限制差異搜尋範圍', '只檢查參照機體與待測有效取樣區重疊的位置。', ('trace-effective-mask.png',)),
    ('校正拍攝明暗', '估計正常圖在這次拍攝條件下會有多亮。', ('reference.png', 'trace-brightness.png')),
    ('找出兩種容差的差異', '一條路容許邊緣小偏移，另一條補找靠邊的小東西。', ('trace-residual-main.png', 'trace-residual-tight.png')),
    ('找出過門檻的差異', '白色是需要繼續檢查的像素。', ('trace-binary-main.png', 'trace-binary-tight.png')),
    ('清碎點並把相連像素分組', '把連在一起的差異交給後續逐個區塊檢查。', ('trace-opened-main.png', 'trace-components-main.png')),
    ('核對原有結構', '兩邊已有的相似結構可能只是位置稍微移動。', ('structure_ref_1.png', 'structure_target_1.png')),
    ('補找容易漏掉的候選', '依既有規則補找小差異、碎片和遮擋外露部位。', ()),
    ('換回原拍攝座標', '人員能回原圖找到工作座標上的候選。', ('candidate',)),
    ('整理送判證據', '保留差異圖和候選位置供逐框追查。', ('difference.png',)),
    ('定位待判候選', '從參照和待測的相同位置找對應內容。', ('candidate', 'reference-candidate')),
    ('選一般物件或外露部位路徑', '外露部位另有自己的裁切和信心條件。', ()),
    ('裁出模型要看的區域', '以下保存實際送進前處理後的模型影像。', ('dino',)),
    ('計算 DINO 特徵', '用小圖和螺絲、正常範例比較。', ('dino',)),
    ('比較參照與待測分數', '待測像螺絲且參照不像，才可能留下警報。', ()),
    ('依條件重看候選', '雙尺寸、完整輪廓等分支只在適用時執行。', ()),
    ('決定是否需要 5r 再看', '5r 只重看前一輪留下的警報。', ()),
    ('保護可能被遮住的小螺絲', '警報複核若要移除，再依既有規則檢查緊密局部。', ()),
    ('保存最終影像與判斷', '可回查原圖、警報疊圖和每個候選的判斷。', ('overlay.png', 'all_overlay.png')),
)


def register(app, root, detection_lock, detect, threshold):
    endpoint = '/engineer/image-trace'
    app.config['XRAY_IMAGE_TRACE'] = True

    @app.route(endpoint, methods=['GET', 'POST'])
    def engineering_image_trace():
        if request.method == 'GET':
            return render_template('engineering_image_trace.html')
        uploads = []
        for field in ('reference', 'target'):
            file = request.files.get(field)
            suffix = Path(file.filename or '').suffix.lower() if file else ''
            if suffix not in SUFFIXES:
                return render_template('engineering_image_trace.html', error='請選擇兩張 PNG、JPEG 或 TIFF 照片。'), 400
            uploads.append((field, suffix, file))
        run = uuid4().hex
        directory = root / run
        directory.mkdir(parents=True)
        inputs = []
        try:
            for field, suffix, file in uploads:
                path = directory / (field + '-input' + suffix)
                file.save(path)
                inputs.append(path)
            with detection_lock, trace.capture(directory) as record, trace.stage('工程檢測全程'):
                result = detect(*inputs, run, threshold(), output_directory=directory)
        except (ValueError, OSError, cv2.error) as exc:
            rmtree(directory, ignore_errors=True)
            return render_template('engineering_image_trace.html', error=str(exc)), 400
        candidates = sorted(result['candidates'] + result['filtered_candidates'], key=lambda c: c['id'])
        dino_images = defaultdict(list)
        for key, name in record['images'].items():
            if key.startswith('dino-'):
                dino_images[int(key.split('-')[1])].append(name)
        for c in candidates:
            number = c['id']
            c['debug_images'] = [name for name in (f'crop_{number}.png', f'reference_crop_{number}.png',
                *dino_images[number])
                if (directory / name).is_file()]
        steps = list(STEPS)
        for step_index, names in ((16, ('crop',)), (18, ('crop', 'reference_crop'))):
            if candidates:
                number = candidates[0]['id']
                title, note, _ = steps[step_index]
                steps[step_index] = (title, note, tuple(f'{name}_{number}.png' for name in names))
        from engineering_report import write_report
        write_report(app, directory, run, result, candidates, record, steps)
        return render_template('engineering_image_trace.html', report=url_for('engineering_trace_asset', run=run, name='report.html'))

    @app.get(endpoint + '/<run>/<name>')
    def engineering_trace_asset(run, name):
        if len(run) != 32 or any(c not in '0123456789abcdef' for c in run):
            abort(404)
        if name != 'report.html':
            abort(404)
        return send_from_directory(root / run, name)
