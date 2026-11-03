"""Show every remaining V10 priority candidate with its reference crop."""
import sys,json,html
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from PIL import Image
from detector import prioritize

ROOT=Path('workspace/windows-check/diagnostics/collected-data')

def main():
    items=json.loads((ROOT/'remaining-56/index.json').read_text(encoding='utf-8'))
    evidence={r['number']:r['evidence'] for r in json.loads((ROOT/'wire-experiment.json').read_text())}
    selected=[r for r in items if not prioritize(dict(r['candidate'],wire_review=evidence[r['number']]))]
    assert len(selected)==6
    out=ROOT/'priority-six';out.mkdir(exist_ok=True)
    cards=[]
    for i,row in enumerate(selected):
        n=row['number'];name=html.escape(row['filename'])
        cards.append(f'<article id="c{n}"><h2>#{n:02d} · {name}</h2><p><a href="remaining-56/{row["sha256"]}-location.png" target="_blank">查看整機位置</a> · <a href="remaining-56/{n:02d}-plain.png" target="_blank">查看無紅框圖片</a></p><img src="remaining-56/{n:02d}.png" alt="候選 {n} 左參照右待測"></article>')
    for page in range(3):
        sheet=Image.new('RGB',(920,1000),'white')
        for j,row in enumerate(selected[page*2:page*2+2]):
            with Image.open(ROOT/'remaining-56'/f'{row["number"]:02d}.png') as im:sheet.paste(im,(0,j*500))
        sheet.save(out/f'pair-{page+1}.png')
    (out/'index.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2),encoding='utf-8')
    body='''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V10 剩餘六個優先紅框</title><style>body{max-width:1000px;margin:35px auto;padding:0 16px;font:18px/1.7 sans-serif;color:#183641}article{border-top:1px solid #ccd5db;padding:20px 0}img{max-width:100%;height:auto}a{color:#007c84}</style><h1>V10：剩餘 6 個優先紅框</h1><p>編號沿用先前 56 個候選對照頁。每張左側是唯一參照圖 cnd64409qy.tiff，右側是待測良品；紅框標示兩圖相同座標。共同比較的 48 張照片仍有 56 個候選，其中這 6 個維持優先紅框，另外 50 個保留複核。</p><p>前五個集中於相近的深色邊角區域，第六個位於線材附近；這是影像外觀描述，並非已確認零件名稱或正常判定。</p>'''+''.join(cards)+'</html>'
    (ROOT/'priority-six-gallery.html').write_text(body,encoding='utf-8')
    print('Verified six priority candidates:',[r['number'] for r in selected])

if __name__=='__main__':main()
