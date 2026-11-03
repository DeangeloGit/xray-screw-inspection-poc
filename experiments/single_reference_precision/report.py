"""Summarize positive and negative results without claiming unmeasured recall."""
import json
import html
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import numpy as np

ROOT=Path('workspace/windows-check/diagnostics/collected-data')
def read(name):return json.loads((ROOT/name).read_text(encoding='utf-8'))
def key(c):return tuple(c[k] for k in ('x','y','w','h'))

def main():
    base=read('single-reference-experiment.json')
    old={r['sha256']:{key(c) for c in r['removed']} for r in base}
    names={'context-consensus':'多個可能位移的一致性','blur':'候選外圍估計模糊程度','line-context':'細線兩端的亮度推估','transport':'舊位置消失＋雙向物體配對','tone-curve':'非線性灰階曲線＋區域交叉驗證'}
    table=[]
    for method,label in names.items():
        rows=read(method+'-experiment.json')
        extra=[(r,c) for r in rows for c in r['removed'] if key(c) not in old[r['sha256']]]
        good=sum('/OK/' in r['relative'] for r,c in extra);ng=sum('/NG/' in r['relative'] for r,c in extra)
        table.append(f'<tr><td>{label}</td><td>{good}</td><td>{ng}</td></tr>')
    rows=read('transport-experiment.json');changed=[r for r in rows if r['removed']]
    font=ImageFont.truetype('C:/Windows/Fonts/msjh.ttc',15)
    canvas=Image.new('RGB',(1000,600),'white');draw=ImageDraw.Draw(canvas)
    for i,r in enumerate(changed):
        z=np.load(r['alignment']);c=r['removed'][0];e=c['single_reference_evidence']
        x,y,w,h=[c[k] for k in ('x','y','w','h')];dx,dy=e['dx'],e['dy']
        draw.text((0,i*300),r['relative'],font=font,fill='black')
        for j,(label,a,cx,cy) in enumerate([('參照圖：原位置',z['ref'],x+dx,y+dy),('待測圖：原位置已消失',z['target'],x+dx,y+dy),('待測圖：新位置',z['target'],x,y)]):
            xx,yy=cx-12,cy-12
            tile=Image.fromarray(np.uint8(a[yy:cy+h+12,xx:cx+w+12]*255)).convert('RGB')
            d=ImageDraw.Draw(tile);d.rectangle((12,12,12+w,12+h),outline='red')
            tile=tile.resize((230,230));canvas.paste(tile,(j*330,i*300+55));draw.text((j*330,i*300+28),label,font=font,fill='black')
    if changed:canvas.save(ROOT/'transport-examples.png')
    body='''<!doctype html><meta charset="utf-8"><title>單張參照誤報研究</title><style>body{font:18px/1.7 sans-serif;max-width:1100px;margin:40px auto;color:#183641}td,th{border:1px solid #cbd5d9;padding:12px}table{border-collapse:collapse;width:100%}img{max-width:100%}</style>
<h1>單張參照：剩餘誤報研究</h1><p><strong>後續更新：</strong>本頁使用原參照的研究結果，不能概括為演算法無法改善。<a href="replacement-reference-report.html">更換單張參照的控制實驗</a>顯示共同 48 張候選由 662 降至 56，原參照選擇是大量誤報的主要因素。</p><p>2026-11-03。正式版維持 V9，以下五種方法均為離線實驗，未部署刪框。每次推論僅讀同機種的一張參照圖及一張待測圖。資料集只用來評估，不參與當次判斷。</p>
<h2>五種方法的實測</h2><p>固定門檻 0.13、185 張；表格為相對 V9 額外排除數，沒有把 V9 已改善的四個重複計算。</p><table><tr><th>方法</th><th>額外排除的 OK 候選</th><th>排除的 NG 候選</th></tr>'''+''.join(table)+'''</table>
<p>初版物體配對曾排除額外 2 個良品候選，但新增遮擋測試發現誤刪風險。禁止物體本身參與亮度擬合後，額外改善歸零。因此五個方向目前都沒有可部署的額外收益。這批資料已多次用於演算法探索，不視為全新獨立測試集。沒有完整螺絲框標註，因此無法計算真實 precision / recall；NG 候選全部保留也不代表所有螺絲已找到。</p>
<h2>剩餘誤報的兩種情況</h2><p><a href="mpt12-151-gallery.html">查看 MPT12 151 個候選的完整 49 張逐圖對照</a></p><p>MPT10 以線材、細邊緣與深淺變化為主。MPT12 的部分誤報呈現真實局部輪廓差異，不能全歸因於亮度。151 個候選集中於同一小零件區域，遍及 49 張良品；另外兩組位置各有 92、84 個候選。這是資料診斷，沒有把座標做成忽略區，也沒有讓其他良品進入推論。</p>
<p>以下每格左邊是唯一參照圖、右邊是待測良品。部分零件數目／排列和線材位置確實不同，僅靠放寬差分條件會同時容忍真的新增物體。</p><img src="remaining-montage-0.png"><p>MPT10 例子：</p><img src="remaining-montage-1.png">
<h2>物體移位規則的保護測試</h2><p>必須同時滿足：形狀唯一配對、原位置確實變亮／清空、出現與消失的差分量相近、反向配對回到原位置。僅附近存在相似螺絲不算證據。</p><p>初版錯誤：若用物體本身估計亮度，新增的深色遮擋也可能被吸收。修正為只用外圍估計後，這批資料的額外排除數為零。原型留存供研究，未接入正式檢測。</p>
<h2>檢查與下一步</h2><p>已驗證「原物體移動」和「原物體仍在、旁邊新增一個」會得到不同判斷；額外加深被解釋區域時必須保留。五個實驗均未排除資料集中原有 NG 候選。對真實零件排列差異，需加入物體類別判斷與真實螺絲標註驗證，不能靠位置黑名單或寬鬆灰階規則達成安全刪框。此方向的模型訓練可使用案例，實際推論仍可維持一張參照圖。</p>
<p>重跑：從專案根目錄執行 .venv/Scripts/python.exe experiments/single_reference_precision/evaluate.py transport（亦可使用 context-consensus、blur、line-context、tone-curve），再執行同資料夾 verify.py 與 report.py。詳細結果保存於各 *-experiment.json。</p>'''
    (ROOT/'precision-research-report.html').write_text(body,encoding='utf-8')
    print(ROOT/'precision-research-report.html')

if __name__=='__main__':main()
