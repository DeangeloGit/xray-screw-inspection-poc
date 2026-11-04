"""Plain-language second pilot report, all 17 fixed cases, no production changes."""
import sys,html,json
from pathlib import Path
from collections import Counter
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.dino.focused_object_pilot import OUT,PRIOR,read,save,guarded,RULES
from experiments.dino.local_added_object_pilot import font,digest
from experiments.dino.local_added_object_report import CSS
def main():
    plan=read(PRIOR/'plan.json');cases=plan['cases'];results=read(OUT/'results.json');old=read(PRIOR/'results-v3.json')
    assert [z['key'] for z in cases]==[z['key'] for z in results]
    for i,z in enumerate(results):
        assert z['extraction']=='ok'
        assert z['baseline_guard']==guarded(old[i]['target']['screw_margin'],old[i]['reference']['screw_margin'])
    stats={mode:{kind:dict(Counter((r['baseline_guard'] if mode=='guard' else 'keep' if r['variants'][mode]['paired_keep'] else 'exclude') for c,r in zip(cases,results) if c['expected']==kind)) for kind in ['new','normal']} for mode in ['guard','focused','soft_background']}
    save(OUT/'summary.json',dict(total=17,new_screw_positions=2,normal_positions=15,stats=stats,scope='same fixed 17, exploratory only',detection_flow_changed=False))
    nav='<nav><a href="index.html">先看結果</a><a href="normal.html">正常案例對照</a><a href="method.html">做法與數據</a></nav>'
    def write(name,title,body):
        (OUT/name).write_text('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>'+title+'</title><style>'+CSS+'</style><main>'+nav+body+'</main></html>',encoding='utf-8')
    words={'keep':'保留：疑似螺絲','review':'保留：待確認','exclude':'排除'}
    def card(n):
        z=cases[n-1];r=results[n-1];v=r['variants']['soft_background'];photo=Path(z['source']);category=z['category'];machine=z['machine']
        links=f'<a href="normal.html#machine-{machine}">返回此機種</a> · <a href="normal.html#category-{machine}-{category}">查看同類案例</a>' if n>2 else '<a href="index.html">返回兩顆螺絲總覽</a>'
        body=f'<article id="case-{n}"><h3>{n}. {html.escape(z["title"])} · {machine}／位置 {z["id"]}</h3><p>原 r2：排除。　<b>只加「保留不確定」：{words[r["baseline_guard"]]}。</b></p>'
        body+=f'<img src="../{PRIOR.name}/images/{n}-pair.jpg" class="pair" loading="lazy"><p class="note">左：正常參照；右：待測。紅框為原本候選位置，正式框沒有修改。{html.escape(z["basis"])}</p>'
        body+=f'<details'+(' open' if n<=2 else '')+'><summary>查看完整取圖、背景處理與 DINO 結果</summary>'
        body+='<div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px">'
        for title,src in [('原本 DINO 待測小圖',f'../{PRIOR.name}/images/{n}-dino-target.png'),('依差分補完整的待測小圖',f'images/{n}-focused-target.png'),('壓淡背景的待測小圖',f'images/{n}-soft_background-target.png')]:body+=f'<figure><figcaption>{title}</figcaption><img src="{src}" style="width:224px"></figure>'
        body+='</div><p>以上都是實際送入 DINO 的圖片。完整取圖與壓淡背景僅用於實驗。</p>'
        if n==1:body+='<p><b>進展：</b>待測圖已從「不像螺絲」變成「像螺絲」。<br><b>仍卡住：</b>參照圖也被判成螺絲，因此沿用原雙圖規則還是會刪除。</p>'
        elif n==2:body+='<p><b>進展：</b>待測仍判螺絲，新的參照取圖改判非螺絲，原雙圖規則可保留這顆。只加「保留不確定」也能保住，但列待確認。</p>'
        body+=f'<p>壓淡背景後：待測判為「{"螺絲" if v["target"]["label"]=="screw" else "非螺絲"}」、參照判為「{"螺絲" if v["reference"]["label"]=="screw" else "非螺絲"}」；雙圖最後：{"保留" if v["paired_keep"] else "排除"}。</p>'
        body+=f'<div class="tiles"><figure><figcaption>自動取出的範圍（綠色）</figcaption><img src="images/{n}-mask.png" style="width:224px"></figure><figure><figcaption>壓淡背景後的參照小圖</figcaption><img src="images/{n}-soft_background-reference.png"></figure></div></details><p class="note">來源：{html.escape(z["name"])}。</p><p><a href="{(photo/"reference.png").as_uri()}">完整參照圖</a> · <a href="{(photo/"aligned.png").as_uri()}">完整待測圖</a> · {links}</p></article>'
        return body
    table='''<table><tr><th>測法（各自單獨比較）</th><th>2 個新增螺絲</th><th>15 個正常對照</th></tr><tr><td>目前 r2</td><td>2 個誤刪</td><td>15 個排除</td></tr><tr><td>只補完整取圖，沿用雙圖判斷</td><td>1 保留／1 誤刪</td><td>15 個排除</td></tr><tr><td>完整取圖＋壓淡背景，沿用雙圖判斷</td><td>1 保留／1 誤刪</td><td>15 個排除</td></tr><tr><td><b>原取圖，只加「保留不確定」</b></td><td><b>2 個保留待確認</b></td><td><b>15 個排除</b></td></tr></table>'''
    body='''<h1>下一步改善：先避免把不確定的螺絲刪掉</h1><div class="answer"><h2>同一批小實驗：兩顆可保留待確認，沒有多出正常案例。</h2><p>採用「分數差很小，就不要直接刪除」這條實驗規則：<b>兩顆螺絲都保留待確認，15 個正常對照仍排除。</b></p><p>這不是把兩顆都自動認對，也不是整批零誤報；只是在這 17 個固定案例中避免誤刪。正式流程尚未修改。</p></div><h2>具體做法是什麼？</h2><ol><li><b>先保留不確定：</b>待測圖在「螺絲／正常」之間差很小，或參照圖只是勉強被判成螺絲，都列「待確認」，不直接排除。</li><li><b>再改善取圖：</b>從原差分框往外找相連的新增深色區域，補出完整範圍，置中取成正方形；另試把周圍背景壓淡，讓 DINO 專注物件。使用同一套規則處理全部 17 例，沒有手寫這兩顆的座標。</li></ol><p>兩個方向分開測，沒有把各案例最好的答案拼成一個結果。這次仍使用原來 47 張螺絲＋65 張正常範例，沒有拿測試案例新增訓練。</p>'''+table+'''<h2>你指定的兩顆：到底改善在哪？</h2><p>取完整、壓淡背景後，<b>兩張待測圖都被 DINO 判成螺絲</b>；但斜螺絲的參照圖仍判錯，所以裁圖改法尚不能直接套用。</p>'''+card(1)+card(2)+'''<h2>正常線材有沒有一起放進來？</h2><p>有。與上次完全相同的 8 個線材＋7 個原有物件／板件，共 15 個正常對照，一個都沒有換掉。上表的最後一項未增加正常待確認或誤報。</p><p><a href="normal.html">按機種 → 類型 → 位置，看全部正常對照 →</a></p><h2>建議下一步</h2><p><b>優先驗證「保留不確定」，暫不啟用背景處理。</b>它改動較小，這批可避免兩顆被直接刪除。但這條規則是在知道兩顆錯誤後提出，仍需其他獨立照片驗證，才能判斷是否值得放進正式流程。</p><p>背景處理還有一個問題：把待測的輪廓套到參照圖，可能產生原本不存在的邊界；而且不壓背景、只換取圖時，斜螺絲參照也會誤判。不能把這項實驗說成已解決雙圖辨識。</p><p class="note">本次只讀既有圖片並對固定 17 例做離線推論；沒有重跑整批差分。來源清單的 UI 修正是另外一件事，不改 DINO 判斷流程。</p>'''
    write('index.html','同批案例改善實驗：先保留不確定',body)
    body='<h1>正常案例：同一批 15 個，全數對照</h1><p>這 15 個在「只加保留不確定」規則下皆維持排除；這是小樣本結果，不能換算成整批準確率。</p>'
    for machine in ['MPT10','MPT11','MPT12','KPH33']:
        ns=[n for n,z in enumerate(cases,1) if n>2 and z['machine']==machine]
        body+=f'<section id="machine-{machine}"><h2>{machine}：{len(ns)} 個正常對照</h2>'
        for category in ['線材','板件邊界','元件外觀','U 形結構','待確認']:
            sub=[n for n in ns if cases[n-1]['category']==category];body+=f'<div id="category-{machine}-{category}"><h3>{category}：{len(sub)} 個位置</h3>'
            if sub:
                body+=card(sub[0])
                if len(sub)>1:body+=f'<details><summary>展開其餘 {len(sub)-1} 個同類位置</summary>'+''.join(card(n) for n in sub[1:])+'</details>'
            else:body+='<p>本次小樣本未選入此類，數量為 0。</p>'
            body+='</div>'
        body+='</section>'
    body+='<script>function openCase(){const n=document.getElementById(decodeURIComponent(location.hash.slice(1)));for(let p=n;p;p=p.parentElement)if(p.tagName==="DETAILS")p.open=true;if(n)n.scrollIntoView()}openCase();addEventListener("hashchange",openCase);</script>'
    write('normal.html','全部正常案例',body)
    body='''<h1>方法與逐例數據</h1><p>分數是「最像的 3 張螺絲平均相似度，減去最像的 3 張正常平均相似度」，不是機率。原版以 0 為分界，實驗另劃 ±0.02 為不確定範圍。</p><ol><li>待測差值低於 −0.02：排除。</li><li>待測差值介於 −0.02 和 +0.02（含端點）：保留待確認。</li><li>待測差值高於 +0.02：參照差值至少 +0.02 時排除；參照在 −0.02 與 +0.02 之間時保留待確認；參照不高於 −0.02 時保留疑似螺絲。</li></ol><p>這個範圍是看過兩個錯誤後提出的探索設定，不是獨立測試得到的最佳門檻。另測 ±0.01、±0.03、±0.05，在同一批也都是兩顆待確認、15 個正常排除；±0.005 則仍誤刪斜螺絲。不能推論其他照片一定相同。</p><p>完整取圖：原候選向外 32 像素，在對齊與明暗調整後，以差值 0.08 選出與原候選重疊最多的相連區域；外加 8 像素並保留正方形全範圍。背景處理：保留物件及外擴 2 像素，其餘保留 25% 原影像、75% 以背景中間亮度取代。參照用相同位置與輪廓。所有參數於本輪執行前固定，沒有依個案調整。</p>'''+table+'<table><tr><th>案例</th><th>原待測差值</th><th>原參照差值</th><th>保留不確定的結果</th></tr>'
    sensitivity=[]
    for band in [.005,.01,.02,.03,.05]:
        outcomes=[]
        for z in old:
            t=z['target']['screw_margin'];r=z['reference']['screw_margin'];outcomes.append('exclude' if t < -band else 'review' if abs(t)<=band else 'exclude' if r>=band else 'review' if abs(r)<band else 'keep')
        sensitivity.append(dict(band=band,new=outcomes[:2],normal=dict(Counter(outcomes[2:]))))
    save(OUT/'sensitivity.json',sensitivity)
    for n,r in enumerate(results,1):
        link=('index.html' if n<=2 else 'normal.html')+f'#case-{n}'
        body+=f'<tr><td><a href="{link}">{n} · {cases[n-1]["machine"]} #{cases[n-1]["id"]}</a></td><td>{r["baseline_target"]:.5f}</td><td>{r["baseline_reference"]:.5f}</td><td>{words[r["baseline_guard"]]}</td></tr>'
    body+='</table><p><a href="plan.json">固定案例</a> · <a href="rules.json">實驗規則</a> · <a href="results.json">完整結果</a> · <a href="summary.json">統計</a> · <a href="sensitivity.json">範圍比較</a> · <a href="preservation.json">原資料未改核對</a></p>'
    write('method.html','實驗方法與數據',body)
    canvas=Image.new('RGB',(1000,1150),'#f4f7f8');d=ImageDraw.Draw(canvas)
    d.text((25,18),'改善小實驗：兩顆可保留「待確認」',font=font(30),fill='#173d4b')
    d.text((25,65),'同一批 15 個正常對照仍排除；正式 DINO 流程尚未修改。',font=font(23),fill='#173d4b')
    for row,n in enumerate([1,2]):
        y=120+row*500;d.text((25,y),'斜螺絲：原版誤刪 → 保留待確認' if n==1 else '圓頭螺絲：原版誤刪 → 保留待確認',font=font(25),fill='#173d4b')
        for j,(label,name) in enumerate([('原本 DINO 的正常參照圖',f'../{PRIOR.name}/images/{n}-dino-reference.png'),('原本 DINO 的待測圖',f'../{PRIOR.name}/images/{n}-dino-target.png')]):
            d.text((25+j*490,y+45),label,font=font(22),fill='#173d4b');im=Image.open(OUT/name).resize((420,420));canvas.paste(im,(25+j*490,y+75))
    d.text((25,1120),'此結果只加「保留不確定」；完整取圖、壓淡背景是另外的實驗。',font=font(20),fill='#173d4b')
    canvas.save(OUT/'summary.png')
    changed=[p for p,v in plan['hashes'].items() if digest(Path(p))!=v]
    # The simultaneous folder-list fix only updates this test fixture locator.
    assert set(changed)<= {str(ROOT/'verify_source_scope.py')},changed
    save(OUT/'preservation.json',dict(unchanged_protected_files=len(plan['hashes'])-len(changed),formal_model_changed=False,
        formal_detection_changed=False,test_harness_updated_separately=changed))
    print(json.dumps(stats))
if __name__=='__main__':main()
