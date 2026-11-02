"""Export confirmed screws plus an explicit unresolved-photo list, never imply a pass."""
import csv
import io
from datetime import datetime, timezone, timedelta

HEADERS = ['序號', 'SN', '照片檔名', '來源完整路徑', '本機影像路徑', '人工判定', '複判時間（台北）', '分析紀錄', '取得時間', '模型版本', '檢測機型', '參考圖 SHA-256', '資料類型', '處理狀態', '未完成原因']


def safe_cell(value):
    value = str(value or '')
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t','\r','\n')) else value


def report_rows(entries):
    rows = []
    for item, result in entries:
        review = result.get('image_review', {})
        issue = result.get('report_issue')
        if review.get('decision') != 'screw' and not issue:
            continue
        for event in item['events']:
            at = datetime.fromisoformat(review['at']).astimezone(timezone(timedelta(hours=8))).isoformat(timespec='seconds') if review.get('at') else ''
            rows.append(dict(sn='', filename=event['filename'], source_path=event['source_path'],
                             local_path=event['local_path'], decision='未判定' if issue else '人工確認有掉落螺絲',
                             reviewed_at=at, run=result.get('name',''), acquired_at=event.get('acquired_at',''),
                             model=result.get('model',{}).get('model_id','未記錄'),
                             machine=result.get('machine',{}).get('name','預設機型（原 V1）'),
                             reference_sha256=result.get('machine',{}).get('reference_sha256',''),
                             kind='待處理異常' if issue else '螺絲結果',
                             status=issue['status'] if issue else '已複判', reason=issue['reason'] if issue else ''))
    return rows


def export_csv(entries):
    out = io.StringIO(newline='')
    writer = csv.writer(out); writer.writerow(HEADERS)
    rows = report_rows(entries)
    for index, row in enumerate(rows,1):
        writer.writerow([index, '', *[safe_cell(row[key]) for key in (
            'filename','source_path','local_path','decision','reviewed_at','run','acquired_at',
            'model','machine','reference_sha256','kind','status','reason')]])
    return ('\ufeff' + out.getvalue()).encode('utf-8'), sum(row['kind']=='螺絲結果' for row in rows)
