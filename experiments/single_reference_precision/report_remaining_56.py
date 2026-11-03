"""Show every remaining candidate on the same 48 paired MPT12 targets."""
import json,html
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont

ROOT=Path('workspace/windows-check/diagnostics/collected-data')
DATA=ROOT/'replacement-reference'
OUT=ROOT/'remaining-56'

def read(path):return json.loads(path.read_text(encoding='utf-8'))

def main():
    OUT.mkdir(exist_ok=True)
    original=read(ROOT/'benchmark-plan.json')['references']['MPT12']['sha256']
    plan=read(DATA/'plan.json');reference=Path(plan['reference']['path']).name
    rows=sorted([read(p) for p in DATA.glob('*/result.json')],key=lambda r:r['relative'])
    rows=[r for r in rows if r['sha256']!=original]
    assert len(rows)==48 and sum(r['count'] for r in rows)==56
    font=ImageFont.truetype('C:/Windows/Fonts/msjh.ttc',19)
    small=ImageFont.truetype('C:/Windows/Fonts/msjh.ttc',16)
    cards=[];manifest=[];panels=[];number=0;photo_count=0
    for row in rows:
        if not row['candidates']:continue
        photo_count+=1
        z=np.load(DATA/row['sha256']/'aligned.npz')
        ref,target=z['ref'],z['target'];height,width=target.shape
        overview=Image.fromarray(np.uint8(np.clip(target,0,1)*255)).convert('RGB')
        od=ImageDraw.Draw(overview)
        for candidate in sorted(row['candidates'],key=lambda c:(c['y'],c['x'])):
            number+=1;n=f'{number:02d}'
            x,y,w,h=(candidate[k] for k in ('x','y','w','h'))
            size=max(96,w+48,h+48)
            x0=max(0,min(width-size,x+w//2-size//2));y0=max(0,min(height-size,y+h//2-size//2))
            x1=min(width,x0+size);y1=min(height,y0+size)
            panel=Image.new('RGB',(920,500),'white');draw=ImageDraw.Draw(panel)
            name=Path(row['path']).name
            draw.text((10,5),f'#{n} · {name}',font=font,fill='#173b47')
            for col,(label,arr) in enumerate([('參照圖（同一位置）',ref),('待測良品（已對齊）',target)]):
                tile=Image.fromarray(np.uint8(np.clip(arr[y0:y1,x0:x1],0,1)*255)).convert('RGB').resize((432,432))
                panel.paste(tile,(10+col*460,62));draw.text((10+col*460,34),label,font=font,fill='#173b47')
            panel.save(OUT/f'{n}-plain.png')
            sx,sy=432/(x1-x0),432/(y1-y0)
            for col in range(2):
                left=10+col*460+(x-x0)*sx;top=62+(y-y0)*sy
                draw.rectangle((left,top,left+w*sx,top+h*sy),outline='#df2438',width=2)
            panel.save(OUT/f'{n}.png');panels.append(panel)
            od.rectangle((x-3,y-3,x+w+3,y+h+3),outline='red',width=3)
            od.text((x-3,max(0,y-24)),n,font=font,fill='red')
            record=dict(number=number,filename=name,source=row['path'],reference=plan['reference']['path'],
                        sha256=row['sha256'],candidate=candidate,crop=[x0,y0,x1,y1],
                        coordinate_frame='1536-long-edge aligned reference pixels')
            manifest.append(record)
            overview_url=f'remaining-56/{row["sha256"]}-location.png'
            cards.append(f'''<article id="c{number}" data-search="{n} {html.escape(name.lower())}">
<h2>#{n} · {html.escape(name)}</h2><p>位置 ({x}, {y})；候選大小 {w} × {h} 像素 · <a href="{overview_url}" target="_blank">查看整機位置</a> · <a href="remaining-56/{n}.png" target="_blank">開啟大圖</a></p>
<img loading="lazy" src="remaining-56/{n}.png" data-box="remaining-56/{n}.png" data-plain="remaining-56/{n}-plain.png" alt="候選 {n} 參照與待測局部對照"></article>''')
        overview.thumbnail((1000,1000));overview.save(OUT/f'{row["sha256"]}-location.png')
    assert number==56 and photo_count==32
    # Contact sheets provide a compact complete set; individual cards remain readable.
    for page,start in enumerate(range(0,len(panels),8),1):
        sheet=Image.new('RGB',(1840,2000),'white')
        for j,panel in enumerate(panels[start:start+8]):sheet.paste(panel,((j%2)*920,(j//2)*500))
        sheet.save(OUT/f'contact-{page}.png')
    preview=Image.new('RGB',(1380,750),'white')
    for j,panel in enumerate(panels[:4]):preview.paste(panel.resize((690,375)),((j%2)*690,(j//2)*375))
    preview.save(ROOT/'remaining-56-preview.png')
    (OUT/'index.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    links=' · '.join(f'<a href="remaining-56/contact-{i}.png" target="_blank">第 {i} 頁（#{(i-1)*8+1:02d}–#{i*8:02d}）</a>' for i in range(1,8))
    body=f'''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MPT12 剩餘 56 個候選</title>
<style>body{{max-width:1040px;margin:30px auto;padding:0 18px;font:18px/1.7 sans-serif;color:#173b47;background:#f7f9fa}}article{{background:white;border:1px solid #dbe3e7;border-radius:12px;margin:22px 0;padding:18px}}h2{{font-size:21px;overflow-wrap:anywhere}}p{{margin:8px 0}}img{{width:100%;height:auto}}.controls{{position:sticky;top:0;background:#edf5f5;padding:12px;z-index:2;border-bottom:1px solid #bed1d5}}input[type=search]{{font:inherit;max-width:100%;padding:8px}}a{{color:#007c84}}article[hidden]{{display:none}}</style>
<h1>MPT12：剩餘 56 個候選逐一對照</h1><p><a href="wire-review-report.html">V10 更新：15 個疑似線材位移提示（全部候選仍保留）</a></p><p>唯一參照圖：<strong>{html.escape(reference)}</strong>。V9、門檻 0.13；共同 48 張待測良品中，32 張有候選、16 張沒有候選。本頁列出全部 56 個，未加入舊參照圖作為待測時的另外 4 個。</p>
<p>每個編號左側是參照圖、右側是待測圖，裁切位置與倍率相同。紅框在兩邊標示同一位置，並非兩邊都偵測到異物。影像已灰階正規化與對齊；可隱藏紅框查看細節。資料夾標為良品，這裡保留「候選」名稱，供你判讀。</p>
<details><summary>七頁總覽（全部 56 個）</summary><p>{links}</p></details>
<div class="controls"><input id="search" type="search" placeholder="搜尋檔名或編號，例如 07"><label><input id="boxes" type="checkbox" checked>顯示紅框</label> <span id="count">56 / 56 個</span></div>
{''.join(cards)}
<script>const cards=[...document.querySelectorAll('article')];document.getElementById('search').addEventListener('input',e=>{{const q=e.target.value.trim().toLowerCase().replace('#','');let n=0;for(const c of cards){{c.hidden=!c.dataset.search.includes(q);if(!c.hidden)n++}}document.getElementById('count').textContent=n+' / 56 個'}});document.getElementById('boxes').addEventListener('change',e=>{{for(const im of document.querySelectorAll('article img'))im.src=e.target.checked?im.dataset.box:im.dataset.plain}});</script></html>'''
    (ROOT/'remaining-56-gallery.html').write_text(body,encoding='utf-8')
    print('PASS: 56 paired candidate cards, 32 photos, 7 contact sheets, plain and boxed images')

if __name__=='__main__':main()
