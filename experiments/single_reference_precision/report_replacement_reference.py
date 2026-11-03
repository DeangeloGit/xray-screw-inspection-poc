"""Report paired targets separately from the two swapped reference images."""
import json,html,statistics
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont

ROOT=Path('workspace/windows-check/diagnostics/collected-data')
OUT=ROOT/'replacement-reference'
def read(p):return json.loads(p.read_text(encoding='utf-8'))

def main():
    plan=read(OUT/'plan.json');newref=plan['reference']
    original=read(ROOT/'benchmark-plan.json')['references']['MPT12']
    before={r['sha256']:r for r in read(ROOT/'single-reference-experiment.json') if r['relative'].startswith('MPT12/')}
    after={r['sha256']:r for r in [read(p) for p in OUT.glob('*/result.json')]}
    assert len(after)==49 and all('count' in r for r in after.values()),'All 49 runs must succeed first'
    common=sorted(before.keys()&after.keys())
    assert len(common)==48
    oldcase=after[original['sha256']]
    assert oldcase['rotation']==0 and not oldcase['mirrored']
    matrix=np.array(oldcase['matrix']);center=matrix@np.array([878.,837.,1.])
    def local_count(cs):return int(sum((c['x']+c['w']/2-center[0])**2+(c['y']+c['h']/2-center[1])**2<22**2 for c in cs))
    # Old grouping is reconstructed exactly, preserving its original insertion order.
    groups=[]
    for row in before.values():
        for c in row['kept']:
            x,y=c['x']+c['w']/2,c['y']+c['h']/2
            g=next((g for g in groups if (g['x']-x)**2+(g['y']-y)**2<22**2),None)
            if g is None:g=dict(x=x,y=y,items=[]);groups.append(g)
            g['items'].append((row['sha256'],c))
    cluster=max(groups,key=lambda g:len(g['items']))
    font=ImageFont.truetype('C:/Windows/Fonts/msjh.ttc',18)
    tiles=[]
    for i,row in enumerate(sorted(after.values(),key=lambda r:r['relative']),1):
        z=np.load(OUT/row['sha256']/'aligned.npz')
        picture=Image.fromarray(np.uint8(np.clip(z['target'],0,1)*255)).convert('RGB')
        d=ImageDraw.Draw(picture)
        for c in row['candidates']:d.rectangle((c['x']-2,c['y']-2,c['x']+c['w']+2,c['y']+c['h']+2),outline='red',width=3)
        picture.thumbnail((650,650));picture.save(OUT/row['sha256']/'overlay.png')
        old=before.get(row['sha256']);oldcount=str(old['after']) if old else '原參照（不計自比）'
        rel=f'replacement-reference/{row["sha256"]}/overlay.png'
        tiles.append(f'<tr><td>{html.escape(Path(row["path"]).name)}</td><td>{oldcount}</td><td><a href="{rel}">{row["count"]}</a></td><td>{local_count(row["candidates"])}</td></tr>')
    # Use a common target fixed in advance by filename, not selected for its count.
    example=next(r for r in after.values() if Path(r['path']).name=='cnd64409qw.tiff')
    oldz=np.load(before[example['sha256']]['alignment']);newz=np.load(OUT/example['sha256']/'aligned.npz')
    canvas=Image.new('RGB',(1000,560),'white');d=ImageDraw.Draw(canvas)
    for col,(label,array,cx,cy) in enumerate([
        ('原參照 cnd64304g5',oldz['ref'],878,837),
        ('新參照 cnd64409qy',newz['ref'],*center),
        ('待測 cnd64409qw',newz['target'],*center)]):
        cx,cy=int(round(cx)),int(round(cy));patch=array[cy-55:cy+55,cx-40:cx+40]
        im=Image.fromarray(np.uint8(np.clip(patch,0,1)*255)).convert('RGB').resize((300,413))
        canvas.paste(im,(col*330,70));d.text((col*330,35),label,font=font,fill='black')
    d.text((5,5),'原本反覆出現候選的局部區域',font=font,fill='black')
    canvas.save(ROOT/'replacement-reference-comparison.png')
    a=sum(before[k]['after'] for k in common);b=sum(after[k]['count'] for k in common)
    summary=dict(reference=Path(newref['path']).name,old_reference=Path(original['path']).name,
        common_images=48,before=a,after=b,reduction=1-b/a,
        common_zero_before=sum(before[k]['after']==0 for k in common),common_zero_after=sum(after[k]['count']==0 for k in common),
        common_median_before=statistics.median(before[k]['after'] for k in common),common_median_after=statistics.median(after[k]['count'] for k in common),
        new_all_count=sum(r['count'] for r in after.values()),new_all_zero=sum(r['count']==0 for r in after.values()),
        old_reference_as_target=oldcase['count'],new_reference_as_old_target=before[newref['sha256']]['after'],
        old_cluster_common=sum(k in common for k,c in cluster['items']),
        new_cluster_common=sum(local_count(after[k]['candidates']) for k in common),
        new_cluster_all=sum(local_count(r['candidates']) for r in after.values()),
        success=49,failed=0,threshold=.13,version=plan['version'])
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    body=f'''<!doctype html><meta charset="utf-8"><title>MPT12 更換單張參照</title>
<style>body{{max-width:1100px;margin:40px auto;font:18px/1.7 sans-serif;color:#183641}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccd5db;padding:10px}}img{{max-width:100%}}</style>
<h1>MPT12 更換唯一參照圖後的結果</h1><p>原參照：{summary['old_reference']}；新參照：{summary['reference']}。新參照在重跑前固定，選用前次已展示的另一張良品，沒有逐一試遍再挑候選最少者。兩組皆使用 V9、門檻 0.13；只換參照、不改演算法，不使用多良品交叉判斷，不改正式機型設定。</p>
<h2>共同 48 張待測良品的公平比較</h2><table><tr><th>項目</th><th>原參照</th><th>新參照</th></tr><tr><td>候選總數</td><td>{a}</td><td>{b}（減少 {100*(1-b/a):.1f}%）</td></tr><tr><td>零候選照片</td><td>{summary['common_zero_before']}</td><td>{summary['common_zero_after']}</td></tr><tr><td>每張候選中位數</td><td>{summary['common_median_before']}</td><td>{summary['common_median_after']}</td></tr><tr><td>原 151 個候選區域（共同照片）</td><td>{summary['old_cluster_common']}</td><td>{summary['new_cluster_common']}</td></tr></table>
<p>兩張參照互換身分，為避免自比造成偏差，以上排除兩張參照本身，只比較共同的 48 張照片。</p>
<h2>新參照完整 49 張測試</h2><p>成功 49、失敗 0；候選總數 {summary['new_all_count']}，其中 {summary['new_all_zero']} 張零候選。原參照現在作為待測圖，產生 {summary['old_reference_as_target']} 個候選。新參照在舊測試中原有 {summary['new_reference_as_old_target']} 個候選。</p>
<h2>原反覆候選區域的對照</h2><img src="replacement-reference-comparison.png"><p>局部統計由舊參照座標映射至新參照附近 22 像素範圍，是區域對照，不是逐物件真值標註。結果支持原參照的局部外觀與多數圖資不同，但不能僅憑此判定它是錯誤機種、不同板本或不良品。</p>
<h2>準確度的解讀</h2><p>依資料夾良品標籤，候選可作為誤報負擔比較。MPT12 沒有真實 NG 標註，因此此結果不能宣稱螺絲辨識準確率或證明換參照後不會漏掉螺絲。此次改善來自參照選擇，不能歸功於算法更新。</p>
<h2>逐張結果（點候選數查看標記圖）</h2><table><tr><th>照片</th><th>舊參照候選</th><th>新參照候選</th><th>原反覆區域</th></tr>{''.join(tiles)}</table>'''
    (ROOT/'replacement-reference-report.html').write_text(body,encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
