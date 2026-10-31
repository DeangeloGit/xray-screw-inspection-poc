"""Analyze current unique data files and save a manifest for engineering review."""
import json
from library import catalog, analyze_sample
from detector import ROOT

def scan():
    rows=[]
    for item in catalog():
        try:
            r=analyze_sample(item)
            row=dict(file=item['filename'],aliases=item['aliases'],sample_id=item['id'],run=r['name'],high=r['high_count'],other=r['review_count'],total=r['proposal_count'],warning=r['alignment_warning'],rotation=r['rotation_ccw'])
        except Exception as e:
            row=dict(file=item['filename'],error=str(e))
        rows.append(row)
        print(json.dumps(row,ensure_ascii=False),flush=True)
        (ROOT/'review/batch_current.json').write_text(json.dumps(dict(samples=rows),ensure_ascii=False,indent=2))
    return rows

if __name__=='__main__':scan()
