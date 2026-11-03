"""Render all 151 V9 candidates in the repeated MPT12 component region."""
import json
import html
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont

ROOT=Path('workspace/windows-check/diagnostics/collected-data')

def main():
    rows=json.loads((ROOT/'single-reference-experiment.json').read_text(encoding='utf-8'))
    groups=[]
    for row in rows:
        if not row['relative'].startswith('MPT12/'):continue
        for c in row['kept']:
            x,y=c['x']+c['w']/2,c['y']+c['h']/2
            group=next((g for g in groups if (g['x']-x)**2+(g['y']-y)**2<22**2),None)
            if group is None:
                group=dict(x=x,y=y,items=[]);groups.append(group)
            group['items'].append((row,c))
    group=max(groups,key=lambda g:len(g['items']))
    assert len(group['items'])==151
    grouped={}
    for row,c in group['items']:
        if row['sha256'] not in grouped:grouped[row['sha256']]=dict(row=row,candidates=[])
        grouped[row['sha256']]['candidates'].append(c)
    assert len(grouped)==49
    folder=ROOT/'mpt12-151';folder.mkdir(exist_ok=True)
    font=ImageFont.truetype('C:/Windows/Fonts/msjh.ttc',19)
    small=ImageFont.truetype('C:/Windows/Fonts/msjh.ttc',14)
    # Fixed crop coordinates for every image; selection only affects the report.
    x0,y0,x1,y1=830,795,920,885
    cards=[];index=[]
    for n,item in enumerate(sorted(grouped.values(),key=lambda r:r['row']['relative']),1):
        row=item['row'];cs=item['candidates'];z=np.load(row['alignment'])
        canvas=Image.new('RGB',(920,500),'white');draw=ImageDraw.Draw(canvas)
        draw.text((10,5),Path(row['relative']).name+f' · {len(cs)} 個候選',font=font,fill='black')
        for col,(key,label) in enumerate([('ref','唯一正常參照圖'),('target','待測良品（已對齊）')]):
            im=Image.fromarray(np.uint8(np.clip(z[key][y0:y1,x0:x1],0,1)*255)).convert('RGB').resize((432,432))
            d=ImageDraw.Draw(im)
            for ci,c in enumerate(cs,1):
                box=((c['x']-x0)*4.8,(c['y']-y0)*4.8,(c['x']+c['w']-x0)*4.8,(c['y']+c['h']-y0)*4.8)
                d.rectangle(box,outline='#e12835',width=2);d.text((box[0],max(0,box[1]-18)),str(ci),font=small,fill='#e12835')
            canvas.paste(im,(10+col*460,62));draw.text((10+col*460,34),label,font=font,fill='black')
        filename=f'{n:02d}.png';canvas.save(folder/filename)
        if row['relative'].endswith('cnd64409qy.tiff'):
            canvas.save(ROOT/'mpt12-151-example.png')
            overview=Image.new('RGB',(1000,800),'white');od=ImageDraw.Draw(overview)
            for col,key in enumerate(['ref','target']):
                im=Image.fromarray(np.uint8(np.clip(z[key],0,1)*255)).convert('RGB')
                d=ImageDraw.Draw(im);d.rectangle((x0,y0,x1,y1),outline='red',width=5)
                im.thumbnail((490,750));overview.paste(im,(col*500,40));od.text((col*500+10,5),'參照圖' if col==0 else '待測良品',font=font,fill='black')
            overview.save(ROOT/'mpt12-151-location.png')
        cards.append(f'<article><h3>{n:02d}. {html.escape(Path(row["relative"]).name)} — {len(cs)} 個</h3><img loading="lazy" src="mpt12-151/{filename}" alt="參照與待測局部對照"></article>')
        index.append(dict(filename=row['relative'],count=len(cs),candidates=cs,alignment=row['alignment']))
    (folder/'index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2),encoding='utf-8')
    plan=json.loads((ROOT/'benchmark-plan.json').read_text(encoding='utf-8'))
    reference=Path(plan['references']['MPT12']['path']).name
    content=f'''<!doctype html><meta charset="utf-8"><title>MPT12：151 個候選逐圖對照</title>
<style>body{{max-width:1100px;margin:35px auto;font:18px/1.7 sans-serif;color:#183641}}img{{max-width:100%;height:auto}}article{{border-top:1px solid #ccd5db;padding:20px 0}}h3{{overflow-wrap:anywhere}}</style>
<h1>MPT12：同一區域的 151 個候選</h1><p>這是 <strong>49 張良品照片累計的 151 個候選框</strong>，不是 151 張照片，也不表示有 151 顆螺絲。同一張照片常有數個框，因為一組局部差異被拆成多個候選。</p>
<p>唯一參照圖：{html.escape(reference)}。V9／門檻 0.13；每組左側是同一張參照圖，右側是不同待測良品。紅框顯示候選位置，也在左圖畫出相同座標方便比較。顯示的是灰階正規化與對齊後影像。</p>
<p>統計方式：候選中心依固定 22 像素半徑分組，本組中心約 (878, 837)，在 1536 像素長邊的對齊座標中。分組只用於整理報告，未用於忽略或刪除候選。框內可見局部深色輪廓／排列差異；僅憑這些 X 光局部圖，不能確定具體零件名稱。</p>
<h2>在整機的位置</h2><img src="mpt12-151-location.png"><h2>全部 49 張照片</h2>{''.join(cards)}'''
    (ROOT/'mpt12-151-gallery.html').write_text(content,encoding='utf-8')
    print('49 photos; 151 candidates; reference:',reference)

if __name__=='__main__':main()
