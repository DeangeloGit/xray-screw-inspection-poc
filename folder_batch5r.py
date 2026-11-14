"""5r folder-level validation. Labels describe photos, never candidate truth."""
import csv
import hashlib
import html
import json
import os
import re
import shutil
import threading
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit
from html.parser import HTMLParser

SUFFIXES = {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp'}
TYPES = ('線材', '板件邊界', '元件外觀', 'U 形結構', '待確認')
FILE_LOCK = threading.RLock()


def save(path, data):
    with FILE_LOCK:
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(path)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def discover(folder):
    folder = Path(folder).expanduser()
    if not folder.is_absolute() or not folder.is_dir():
        raise ValueError('請指定可讀取的完整資料夾路徑')
    folder = folder.resolve()
    label = folder.name.upper().strip('[]')
    if label not in ('NG', 'OK'):
        raise ValueError('請選擇名稱為 NG 或 OK 的資料夾（也支援 [NG]、[OK]）')
    # Do not deduplicate: every source filename is a photo in this evaluation.
    files = []
    def unreadable(error):
        raise ValueError('無法完整列出資料夾：'+str(error))
    for current, dirs, names in os.walk(folder, onerror=unreadable, followlinks=False):
        dirs[:] = [name for name in dirs if not (Path(current)/name).is_symlink()
                   and not (Path(current)/name).is_junction()]
        for name in names:
            path = Path(current)/name
            if path.suffix.lower() in SUFFIXES and not path.is_symlink(): files.append(path)
    files.sort(key=lambda p: p.relative_to(folder).as_posix().casefold())
    if not files:
        raise ValueError('資料夾內沒有支援的圖檔（含子資料夾）')
    return folder, label, files


def summarize(rows):
    valid = [r for r in rows if r['status'] == 'done' and not r['is_reference']]
    return dict(total=len(rows), completed=len(valid),
                errors=sum(r['status'] == 'error' for r in rows),
                reference_self=sum(r.get('is_reference', False) for r in rows),
                ng_total=sum(r['label'] == 'NG' for r in valid),
                ok_total=sum(r['label'] == 'OK' for r in valid),
                ng_missed=sum(r['label'] == 'NG' and r['kept'] == 0 for r in valid),
                ok_false_alarm=sum(r['label'] == 'OK' and r['kept'] > 0 for r in valid),
                alarm_photos=sum(r['kept'] > 0 for r in valid),
                alignment_warnings=sum(bool(r.get('alignment_warning')) for r in valid))


def verdict(row):
    if row['status'] == 'error':
        return '處理失敗（不計入未檢出／誤報）'
    if row['is_reference']:
        return '參照圖自比（獨立列出）'
    if row['label'] == 'NG':
        return '有警報（命中位置待確認）' if row['kept'] else '未檢出掉落螺絲'
    return '誤報有掉落螺絲' if row['kept'] else '未報出掉落螺絲'


def report(directory, job):
    """Complete, standalone report: all files, all retained/excluded candidates."""
    from PIL import Image, ImageDraw
    esc = lambda value: html.escape(str(value), quote=True)
    rows = job['rows']
    groups = defaultdict(list)
    cases = []
    def page(name, title, body):
        (directory / name).write_text('<!doctype html><html lang="zh-Hant"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width"><title>' + esc(title) + '</title>'
            '<style>body{font-family:system-ui;max-width:1200px;margin:auto;padding:24px;color:#173447}'
            'table{border-collapse:collapse}td,th{border:1px solid #ccd8dd;padding:8px}'
            'img{max-width:100%}.pair{display:grid;grid-template-columns:1fr 1fr;gap:12px}'
            'article,section{padding:12px;border:1px solid #ccd8dd;margin:12px 0}</style>'
            + body + '</html>', encoding='utf-8')
    def card(c):
        row, candidate, state, key, group = c
        reference = candidate.get('classification', {}).get('paired_evidence', {}).get('reference', {})
        evidence_note = '<p>待測未達門檻，參照分數未計算。</p>' if reference.get('evaluated') is False else ''
        experiment = candidate.get('classification', {}).get('r4_experiment', {})
        if experiment.get('skipped') == 'geometry_ineligible':
            evidence_note += '<p>物件範圍未達門檻，補提階段的雙尺寸分數未計算。</p>'
        return (f'<article id="case-{key}"><h3>{esc(row["file"])} #{esc(candidate["id"])}：{state}</h3>'
                f'<p>分類：待確認（無人工類型標記） · <a href="machine.html">返回此機種</a> · '
                f'<a href="groups.html#group-{group}">查看同類案例</a> · '
                f'<a href="photo-{row["id"]}.html#case-{key}">查看照片</a></p>'
                + evidence_note + f'<p>左：參照圖；右：待測圖。框數不是螺絲顆數。</p><img loading="lazy" src="images/{key}.jpg"></article>')
    (directory / 'images').mkdir(exist_ok=True)
    for row in rows:
        if row['status'] != 'done':
            continue
        path = directory / 'runs' / row['id']
        result = json.loads((path / 'result.json').read_text(encoding='utf-8'))
        if row['kept'] != len(result['candidates']) or row['removed'] != len(result['filtered_candidates']):
            raise ValueError('照片候選統計不符：'+row['file'])
        local = []
        with Image.open(path / 'reference.png') as im:
            ref = im.convert('RGB')
        with Image.open(path / 'aligned.png') as im:
            target = im.convert('RGB')
        ids = []
        for state, candidates in [('保留警報', result['candidates']), ('排除', result['filtered_candidates'])]:
            for c in candidates:
                ids.append(c['id'])
                x, y, w, h = [int(c[k]) for k in ('x', 'y', 'w', 'h')]
                key = row['id'] + '-' + str(c['id'])
                group = ('self-' if row['is_reference'] else '') + f'{round((x+w/2)/45)}-{round((y+h/2)/45)}'
                item = (row, c, state, key, group)
                local.append(item); cases.append(item); groups[group].append(item)
                side = max(120, w+48, h+48)
                x0, y0 = max(0, x+w//2-side//2), max(0, y+h//2-side//2)
                canvas = Image.new('RGB', (600, 300), 'white')
                for i, image in enumerate((ref, target)):
                    crop = image.crop((x0, y0, x0+side, y0+side))
                    ImageDraw.Draw(crop).rectangle((x-x0, y-y0, x+w-x0, y+h-y0), outline='red', width=2)
                    canvas.paste(crop.resize((300, 300)), (300*i, 0))
                canvas.save(directory / 'images' / (key+'.jpg'), quality=80)
        if len(ids) != len(set(ids)) or len(ids) != result['pre_ai_count']:
            raise ValueError('候選覆蓋數不符：'+row['file'])
        body = (f'<a href="index.html">總結果</a> · <a href="machine.html">返回此機種</a> · '
                f'<a href="groups.html">查看同類案例</a><h1>{esc(row["file"])}</h1>'
                f'<p>{esc(verdict(row))}；分類：待確認；保留 {row["kept"]} 框／排除 {row["removed"]} 框。</p>'
                f'<p>對位警告：{esc(row["alignment_warning"])}</p><div class="pair">'
                f'<div>參照<img src="runs/{row["id"]}/reference.png"></div>'
                f'<div>待測<img src="runs/{row["id"]}/aligned.png"></div></div>'
                f'<a href="runs/{row["id"]}/result.json">完整判斷資料</a>'
                '<h2>全部保留／排除候選</h2>'+(''.join(card(c) for c in local) or '<p>零候選</p>'))
        page('photo-'+row['id']+'.html', row['file'], body)
    for row in rows:
        if row['status'] == 'error':
            page('photo-'+row['id']+'.html', row['file'],
                 '<a href="index.html">總結果</a> · <a href="machine.html">返回此機種</a> · '
                 '<a href="groups.html">查看同類案例</a><h1>'+esc(row['file'])+'</h1><p>分類：待確認；'
                 +esc(verdict(row))+'</p><p>'+esc(row['error'])+'</p>')
    table = ''
    for self_only, heading in [(False, '全部待測照片（含處理失敗）'), (True, '參照圖自比')]:
        table += '<h2>'+heading+'</h2><table><tr><th>圖檔</th><th>標籤</th><th>照片判定</th><th>保留框</th><th>排除框</th></tr>'
        selected = [row for row in rows if row['is_reference'] == self_only]
        for row in selected:
            table += (f'<tr><td><a href="photo-{row["id"]}.html">{esc(row["file"])}</a></td>'
                      f'<td>{row["label"]}</td><td>{esc(verdict(row))}</td><td>{row.get("kept", "—")}</td>'
                      f'<td>{row.get("removed", "—")}</td></tr>')
        table += '</table>' + ('<p>0 張</p>' if not selected else '')
    summary = summarize(rows)
    summary_html = (f'<p>全部 {summary["total"]} 張；完成判定 {summary["completed"]} 張；'
                    f'處理失敗 {summary["errors"]} 張；參照自比 {summary["reference_self"]} 張。</p>'
                    f'<p><b>NG 未檢出：{summary["ng_missed"]}／{summary["ng_total"]} 張；OK 誤報：{summary["ok_false_alarm"]}／{summary["ok_total"]} 張。</b>'
                    f'對位警告 {summary["alignment_warnings"]} 張，請複核。</p>')
    explanation = ('<p>依使用者提供的資料夾標籤統計，每個檔名計一張（含重複影像）。'
                   'NG 無保留警報計為未檢出；OK 有保留警報計為誤報。NG 有警報不保證命中真正螺絲；'
                   '沒有位置答案，不能計算螺絲顆數的命中／漏失。參照自比與失敗另列。</p>')
    page('index.html', '5r 資料夾完整報告', '<h1>5r 本次良品／不良品完整結果</h1>'+summary_html+
         explanation+f'<p>機種：<a href="machine.html">{esc(job["machine"]["name"])}</a>；'
         f'資料夾：{esc(job["folder"])}；標籤：{job["label"]}</p>'
         '<p><a href="photos.csv">下載逐張 CSV</a> · <a href="job.json">批次設定與結果</a></p>'+table)
    page('machine.html', job['machine']['name'], '<a href="index.html">總結果</a><h1>'+esc(job['machine']['name'])+
         '</h1>'+summary_html+'<h2>誤報類型／候選分類</h2><p>尚無人工或自動類型分類，全部列為待確認。</p>'+
         ''.join(f'<p>{t}：{len(cases) if t == "待確認" else 0} 框</p>' for t in TYPES)+
         '<a href="groups.html">待確認 → 相近位置</a><h2>全部照片（參照自比獨立標示）</h2>'+table)
    body = '<a href="machine.html">返回此機種</a><h1>待確認 → 相近位置</h1><p>依座標粗分方便瀏覽，不表示同一物件或人工確認類型。</p>'
    for group, items in groups.items():
        body += f'<section id="group-{group}"><h2>相近位置 {esc(group)}（{len(items)} 框）</h2>'+card(items[0])
        if len(items) > 1:
            body += f'<details><summary>展開全部同類照片／其餘 {len(items)-1} 框</summary>'+''.join(card(c) for c in items[1:])+'</details>'
        body += '</section>'
    page('groups.html', '同類案例', body)
    with (directory / 'photos.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['圖檔', '標籤', '判定', '保留框', '排除框', '錯誤'])
        for r in rows:
            values = [r['file'], r['label'], verdict(r), r.get('kept', ''), r.get('removed', ''), r.get('error', '')]
            writer.writerow(["'"+v if isinstance(v, str) and v.startswith(('=', '+', '-', '@')) else v for v in values])
    return dict(photos=len(rows), candidates=len(cases), summary=summary)


def verify_report(directory, expected):
    class Links(HTMLParser):
        def __init__(self):
            super().__init__(); self.links = []; self.ids = set()
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if 'id' in attrs: self.ids.add(attrs['id'])
            for key in ('src', 'href'):
                if key in attrs: self.links.append(attrs[key])
    pages = {}
    for path in directory.glob('*.html'):
        parser = Links(); parser.feed(path.read_text(encoding='utf-8')); pages[path.resolve()] = parser
    for path, parser in pages.items():
        for link in parser.links:
            url = urlsplit(link)
            if url.scheme or url.netloc: raise ValueError('報告含外部連結')
            target = (path.parent / unquote(url.path)).resolve() if url.path else path
            if not target.is_relative_to(directory.resolve()) or not target.is_file():
                raise ValueError('報告缺少檔案：'+link)
            if url.fragment and unquote(url.fragment) not in pages[target].ids:
                raise ValueError('報告缺少錨點：'+link)
    if len(list(directory.glob('photo-*.html'))) != expected['photos']:
        raise ValueError('照片頁覆蓋數不符')
    count = sum(len([i for i in p.ids if i.startswith('case-')]) for f, p in pages.items() if f.name.startswith('photo-'))
    if count != expected['candidates']: raise ValueError('候選覆蓋數不符')
    return dict(status='passed', **expected)


def register(app, root, detection_lock, model_lock, detect, get_snapshot, get_profile, get_threshold):
    from flask import jsonify, request, render_template, send_from_directory
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    job_lock = threading.Lock()
    active = set()

    @app.get('/5r/batch')
    def folder5r_page():
        return render_template('folder_batch5r.html')

    @app.post('/api/5r/batches')
    def folder5r_start():
        body = request.get_json(silent=True) or {}
        try:
            if not isinstance(body, dict): raise ValueError('請提供資料夾與機種')
            with job_lock:
                if active: return jsonify(error='已有資料夾檢測進行中，請等待完成'), 409
            folder, label, files = discover(body.get('folder', ''))
            profile = get_profile(body.get('machine_id'))
            threshold = get_threshold(profile['id'])
            with model_lock:
                snapshot = get_snapshot()
                if snapshot.error or snapshot.session is None:
                    raise ValueError('DINO 模型不可用，停止批次')
            with job_lock:
                if active: return jsonify(error='已有資料夾檢測進行中，請等待完成'), 409
                token = uuid.uuid4().hex
                directory = root / token
                directory.mkdir()
                reference = directory / ('golden'+Path(profile['reference']).suffix.lower())
                shutil.copyfile(profile['reference'], reference)
                if sha(reference) != profile['reference_sha256']:
                    raise ValueError('正常參照圖已變更，請重新開始')
                job = dict(id=token, state='running', folder=str(folder), label=label,
                           service_version='5r-folder-batch-v1',
                           machine=profile, threshold=threshold, model=snapshot.info(),
                           created_at=datetime.now(timezone.utc).isoformat(),
                           total=len(files), completed=0, current=None, rows=[])
                save(directory/'job.json', job)
                active.add(token)
        except (OSError, ValueError, TypeError) as error:
            return jsonify(error=str(error)), 400

        def work():
            try:
                # The legacy classifier temporarily installs policy callbacks. Keep it
                # serialized with the existing app and freeze the bank for this run.
                with detection_lock, model_lock:
                    for index, source in enumerate(files):
                        row = dict(id=f'{index:06d}', file=source.relative_to(folder).as_posix(),
                                   label=label, status='error', is_reference=False)
                        job['current'] = row['file']; save(directory/'job.json', job)
                        run = directory/'runs'/row['id']; run.mkdir(parents=True)
                        try:
                            before = sha(source)
                            target = run/('input'+source.suffix.lower())
                            shutil.copyfile(source, target)
                            if sha(target) != before or sha(source) != before:
                                raise ValueError('來源圖檔在讀取期間變更，請重試')
                            row['source_sha256'] = before
                            result = detect(reference, target, row['id'], threshold,
                                            model_snapshot=snapshot, output_directory=run)
                            row.update(status='done', is_reference=before == profile['reference_sha256'],
                                       kept=len(result['candidates']), removed=len(result['filtered_candidates']),
                                       alignment_warning=result.get('alignment_warning', False))
                        except Exception as error:
                            row['error'] = str(error)
                        job['rows'].append(row); job['completed'] += 1
                        save(directory/'job.json', job)
                job['current'] = None; job['state'] = 'reporting'; save(directory/'job.json', job)
                expected = report(directory, job)
                save(directory/'verification.json', verify_report(directory, expected))
                job.update(state='done', summary=expected['summary'], report=f'/5r/batches/{token}/index.html',
                           completed_at=datetime.now(timezone.utc).isoformat())
            except Exception as error:
                job.update(state='failed', error=str(error))
            finally:
                try:
                    save(directory/'job.json', job)
                finally:
                    with job_lock: active.discard(token)
        threading.Thread(target=work, daemon=True).start()
        return jsonify(id=token), 202

    @app.get('/api/5r/batches/<token>')
    def folder5r_status(token):
        if not re.fullmatch('[a-f0-9]{32}', token) or not (root/token/'job.json').is_file():
            return jsonify(error='找不到批次'), 404
        with FILE_LOCK:
            job = json.loads((root/token/'job.json').read_text(encoding='utf-8'))
        if job['state'] in ('running', 'reporting') and token not in active:
            job.update(state='interrupted', error='服務已重啟，這批尚未完成；請重新執行')
        return jsonify(job)

    @app.get('/5r/batches/<token>/<path:filename>')
    def folder5r_asset(token, filename):
        if not re.fullmatch('[a-f0-9]{32}', token): return jsonify(error='找不到批次'), 404
        with FILE_LOCK:
            path = root/token/'job.json'
            if not path.is_file(): return jsonify(error='找不到批次'), 404
            job = json.loads(path.read_text(encoding='utf-8'))
        if job['state'] != 'done': return jsonify(error='完整報表尚未核對完成'), 409
        return send_from_directory(root/token, filename)
