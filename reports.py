"""Export a frozen set of completed human reviews, never machine predictions."""
import csv
import io
from datetime import datetime, timezone, timedelta

HEADERS = ['序號', 'SN', '照片檔名', '來源完整路徑', '本機影像路徑', '人工判定', '複判時間（台北）', '分析紀錄', '取得時間', '模型版本']

def safe_cell(value):
    value = str(value or '')
    # Prevent Excel interpreting device-controlled filenames as formulas.
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t','\r','\n')) else value

def export_csv(entries):
    out = io.StringIO(newline='')
    writer = csv.writer(out); writer.writerow(HEADERS)
    index = 0
    for item, result in entries:
        review = result.get('image_review', {})
        if review.get('decision') != 'screw': continue
        for event in item['events']:
            index += 1
            at = datetime.fromisoformat(review['at']).astimezone(timezone(timedelta(hours=8))).isoformat(timespec='seconds')
            writer.writerow([index, '', safe_cell(event['filename']), safe_cell(event['source_path']),
                             safe_cell(event['local_path']), '人工確認有掉落螺絲', at, result['name'],
                             event.get('acquired_at',''), safe_cell(result.get('model',{}).get('model_id','未記錄'))])
    return ('\ufeff' + out.getvalue()).encode('utf-8'), index
