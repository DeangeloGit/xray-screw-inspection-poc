"""Report the requested reference-no/target-yes result, including fragility."""
import sys,json,html,hashlib
from pathlib import Path
from collections import Counter
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.dino.multiscale_pair_pilot import OUT,PRIOR,read,save
from experiments.dino.local_added_object_report import CSS
from experiments.dino.local_added_object_pilot import font

def main():
    plan=read(PRIOR/'plan.json');cases=plan['cases'];rows=read(OUT/'results.json');sensitivity=read(OUT/'sensitivity.json');audit=read(OUT/'overlap-audit.json')
    assert len(rows)==17 and [x['key'] for x in rows]==[x['key'] for x in cases]
    def result(r,pad=0):
        t=next(v for v in r['target']['views'] if v['padding']==pad);ref=next(v for v in r['reference']['views'] if v['padding']==pad)
        return dict(target=t['screw'],reference=ref['screw'],keep=t['screw'] and not ref['screw'],target_margin=t['margin'],reference_margin=ref['margin'])
    tight=[result(r) for r in rows];assert all(r['keep'] for r in tight[:2]);assert not any(r['keep'] for r in tight[2:])
    counts=[]
    for pad in [0,8,16,24,32]:
        rr=[result(r,pad) for r in rows];counts.append(dict(padding=pad,new_correct=sum(r['keep'] for r in rr[:2]),normal_false_alerts=sum(r['keep'] for r in rr[2:])))
    counts.append(dict(padding='five_view_majority',new_correct=sum(r['paired_keep'] for r in rows[:2]),normal_false_alerts=sum(r['paired_keep'] for r in rows[2:])))
    summary=dict(fixed_cases=17,new_positions=2,normal_positions=15,strict_new_pair_correct=2,normal_final_alerts=0,normal_both_false_screw=2,
        crop_variants=counts,sensitivity={str(n):dict(passed=sum(z['paired_keep'] for z in sensitivity if z['number']==n),trials=6) for n in [1,2]},
        exact_normal_example_overlap=len(audit['removed_ids']),leave_identified_normal_examples_out=dict(new_correct=sum(z['paired_keep'] for z in audit['results'][:2]),normal_alerts=sum(z['paired_keep'] for z in audit['results'][2:])),
        formal_flow_changed=False,selection='tight crop selected after inspecting the predefined 5 crop sizes on these development cases; not independent validation')
    save(OUT/'summary.json',summary)
    nav='<nav><a href="index.html">先看兩顆螺絲</a><a href="normal.html">全部正常對照</a><a href="details.html">限制與完整數據</a><a href="folder-fix.html">17 張變 12 張核對</a></nav>'
    def write(name,title,body):
        (OUT/name).write_text('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+title+'</title><style>'+CSS+'</style><main>'+nav+body+'</main></html>',encoding='utf-8')
    def card(n):
        z=cases[n-1];r=tight[n-1];machine=z['machine'];category=z['category'];source=Path(z['source'])
        body=f'<article id="case-{n}"><h3>{n}. {html.escape(z["title"])} · 位置 {z["id"]}</h3><p>{machine}／{category}。<b>參照圖：{"有螺絲" if r["reference"] else "沒有螺絲"}；待測圖：{"有螺絲" if r["target"] else "沒有螺絲"}。</b></p>'
        body+='<p class="note">上面是 DINO 的判斷，不是把人工答案寫進程式；「有／沒有」對應模型的螺絲／非螺絲分類。</p><div class="tiles">'
        for side,label in [('reference','DINO 實際看到的參照圖'),('target','DINO 實際看到的待測圖')]:body+=f'<figure><figcaption>{label}</figcaption><img src="images/{n}-{side}-0.png" style="width:360px"></figure>'
        body+=f'</div><p>雙圖最後：<b>{"保留螺絲候選" if r["keep"] else "排除"}</b>。沒有使用「待確認」替代答案。</p>'
        if n==1:body+='<p class="bad"><b>仍不穩定：</b>取圖向右、向上或向下移 2 像素時，待測螺絲又被判錯。往左移 2 像素仍正確；外加 2 像素仍正確、外加 4 像素則失敗。不能立即套用正式流程。</p>'
        if n==2:body+='<p>另外試了上下左右各移 2 像素、外加 2 或 4 像素，共 6 種小變動，這顆仍都得到「參照沒有、待測有」。這仍只是一顆的局部測試。</p>'
        if n in [12,13]:body+='<p class="bad"><b>正常案例的隱藏錯誤：</b>這裡是良品板件邊界，兩張都被叫作螺絲；只是最後被雙圖規則排除。不能把它算成每張小圖都分類正確。</p>'
        body+=f'<details><summary>看較大範圍，確認原始位置</summary><img class="pair" src="../{PRIOR.name}/images/{n}-pair.jpg"><p>左參照、右待測；紅框仍是原候選框，正式框未更動。</p></details><p class="note">{html.escape(z["name"])}；{html.escape(z["basis"])}。</p>'
        links=f'<a href="normal.html#machine-{machine}">返回此機種</a> · <a href="normal.html#category-{machine}-{category}">查看同類案例</a>' if n>2 else '<a href="index.html">返回兩顆螺絲總覽</a>'
        return body+f'<p><a href="{(source/"reference.png").as_uri()}">完整參照圖</a> · <a href="{(source/"aligned.png").as_uri()}">完整待測圖</a> · {links}</p></article>'
    body='''<h1>這次直接驗證：參照沒有螺絲，待測有螺絲</h1><div class="answer"><h2>兩顆在這次取圖下都判對；斜螺絲仍對取圖位置敏感。</h2><p><b>不把「待確認」算成功。</b>這次的成功條件就是：參照判非螺絲，待測判螺絲。兩顆在貼近輪廓的取圖下都達成。</p><p>同一批 15 個正常對照沒有新增保留框。不過斜螺絲稍微換取圖位置就會判錯，仍不能稱為穩定解決，也沒有套用正式流程。</p></div><table><tr><th>指定案例</th><th>參照圖</th><th>待測圖</th><th>是否達成要求</th></tr><tr><td>斜螺絲 #94</td><td>非螺絲</td><td>螺絲</td><td>本次達成；仍不穩定</td></tr><tr><td>圓頭螺絲 #34</td><td>非螺絲</td><td>螺絲</td><td>本次達成</td></tr></table><h2>具體改哪裡？</h2><ol><li>從原差分候選附近找出相連的新增深色範圍，不手寫這兩顆的座標。</li><li>用這個範圍的中心與較長邊取正方形近照，<b>不另外加一大圈背景</b>。這次是貼近輪廓；不保證所有物件的淡邊都完整，所以還需要穩定性驗證。</li><li>參照圖取<b>完全相同位置、大小</b>，兩邊各交給原 DINO 47＋65 範例判斷。沒有壓淡背景、沒有把待測形狀畫進參照圖，也沒有調低分類門檻。</li></ol><p>測了外加 0、8、16、24、32 像素及多範圍投票；本批是「外加 0」達成兩顆要求。這是在固定開發案例上找方法，不能當成獨立準確率。</p>'''+card(1)+card(2)+'''<h2>正常案例怎麼樣？</h2><p>8 個線材＋7 個原有物件／板件，共 15 個對照，最後都排除，沒有新增保留框。<b>其中 2 個板邊是兩圖都被誤認螺絲、最後靠雙圖規則排除</b>，所以不能說 15 組的每張圖都認對。</p><p><a href="normal.html">查看全部 15 個正常對照 →</a></p><h2>下一個研究重點</h2><p>把斜螺絲在小幅位置、大小改變下也穩定判成「參照沒有、待測有」。本次已找到可判對的取圖，但還沒解決這個穩定性問題。正式 DINO 維持 r2，這輪所有方法只在實驗裡。</p>'''
    write('index.html','兩顆螺絲：參照非螺絲、待測螺絲',body)
    body='<h1>全部 15 個正常對照</h1><p>最後沒有新增保留框；第 12、13 例仍有雙圖都誤認螺絲的分類錯誤，已明確標出。</p>'
    for machine in ['MPT10','MPT11','MPT12','KPH33']:
        ns=[n for n,z in enumerate(cases,1) if n>2 and z['machine']==machine];body+=f'<section id="machine-{machine}"><h2>{machine} · {len(ns)} 個位置</h2>'
        for cat in ['線材','板件邊界','元件外觀','U 形結構','待確認']:
            sub=[n for n in ns if cases[n-1]['category']==cat];body+=f'<div id="category-{machine}-{cat}"><h3>{cat} · {len(sub)} 個位置</h3>'
            if sub:
                body+=card(sub[0])
                if len(sub)>1:body+=f'<details><summary>展開其餘 {len(sub)-1} 個同類位置</summary>'+''.join(card(n) for n in sub[1:])+'</details>'
            else:body+='<p>本次固定小樣本未選入，數量為 0。</p>'
            body+='</div>'
        body+='</section>'
    body+='<script>function show(){const n=document.getElementById(decodeURIComponent(location.hash.slice(1)));for(let p=n;p;p=p.parentElement)if(p.tagName==="DETAILS")p.open=true;if(n)n.scrollIntoView()}show();addEventListener("hashchange",show);</script>'
    write('normal.html','正常對照：機種與類型',body)
    body='<h1>限制與完整數據</h1><p>同一批固定 17 個案例，沒有抽換正常案例。門檻沿用 0、每類最像 3 張平均、47＋65 範例不變。取圖輪廓沿用前輪實驗的自動相連差分區，原圖已對齊，本輪不再另做局部平移。</p><h2>每個取圖範圍都列出</h2><table><tr><th>額外背景</th><th>兩顆中有幾顆符合參照非螺絲／待測螺絲</th><th>15 正常的新增保留框</th></tr>'
    for r in counts:body+=f'<tr><td>{r["padding"] if isinstance(r["padding"],int) else "五個範圍多數決"}</td><td>{r["new_correct"]}／2</td><td>{r["normal_false_alerts"]}</td></tr>'
    body+='</table><p>另測過用既有範例學習新的分類分界，仍把斜螺絲的參照判成螺絲；原取圖下沒有兩顆都過關，故未採用。<a href="../dino-learned-boundary-20261103/results.json">查看該輪全部結果</a>。</p>'
    body+=f'<h2>測試案例有沒有與範例重複？</h2><p>查到 {len(audit["removed_ids"])} 個正常測試案例原本就在正常範例庫。額外移除這些已知重複（僅離線測試）後，以 47 張螺絲＋{audit["normal_examples"]} 張正常重算：兩顆仍達成指定雙圖判斷，15 正常仍沒有保留框。但無法排除其他同源照片或螺絲拼圖重複，因此仍不宣稱獨立準確率。</p>'
    body+='<h2>稍微移動或放寬取圖，有沒有改答案？</h2><table><tr><th>案例</th><th>改動</th><th>參照</th><th>待測</th><th>指定雙圖判斷</th></tr>'
    for r in sensitivity:body+=f'<tr><td>{"斜螺絲" if r["number"]==1 else "圓頭螺絲"}</td><td>左右 {r["dx"]}、上下 {r["dy"]} 像素；外加 {r["padding"]}</td><td>{"螺絲" if r["reference"]["screw"] else "非螺絲"}</td><td>{"螺絲" if r["target"]["screw"] else "非螺絲"}</td><td>{"達成" if r["paired_keep"] else "未達成"}</td></tr>'
    body+='</table><h2>逐例分數（不是機率）</h2><table><tr><th>例</th><th>參照差值</th><th>待測差值</th><th>最後保留</th></tr>'
    for n,r in enumerate(tight,1):body+=f'<tr><td><a href="{"index.html" if n<=2 else "normal.html"}#case-{n}">{n} · {cases[n-1]["machine"]} #{cases[n-1]["id"]}</a></td><td>{r["reference_margin"]:.5f}</td><td>{r["target_margin"]:.5f}</td><td>{"是" if r["keep"] else "否"}</td></tr>'
    body+='</table><p><a href="plan.json">案例固定記錄</a> · <a href="rules.json">取圖規則</a> · <a href="results.json">完整結果</a> · <a href="summary.json">統計</a> · <a href="overlap-audit.json">重複範例核對</a> · <a href="sensitivity.json">取圖偏移測試</a></p>'
    write('details.html','完整數據與未解決問題',body)
    fix=read(ROOT/'workspace/service-updates/20261103-current-folder-inventory/verification.json')
    body='<h1>清單問題：17 張已核對為目前資料夾的 12 張</h1><div class="answer"><p>多出的 5 筆，都是已不在來源資料夾的舊檔案。先前只修畫面更新，沒有修到這個原因。</p><p>這次改為最近一次成功掃描仍存在的檔案版本；舊副本、事件紀錄與人工紀錄都保留。</p></div><p>已部署本機 18766。後端回傳 12 張，檔名集合與資料夾現有影像完全一致。下列核對不是畫面截圖；電腦操作工具因無法確認瀏覽器網址而停止，未完成畫面目視檢查。</p><h2>目前清單：12 張</h2><ol>'+''.join('<li>'+html.escape(name)+'</li>' for name in fix['current_names'])+'</ol><h2>從本批隱藏、歷史仍保留的 5 筆</h2><ul>'+''.join('<li>'+html.escape(z['name'])+'（舊副本仍在）</li>' for z in fix['hidden_history'])+'</ul><p>測試涵蓋：檔案移走、放回、同名檔案被新版取代、來源斷線及不完整讀取。斷線不當成空資料夾；成功掃描後才更新存在狀態。274 個保護檔案與原有事件／複判資料已核對未變，正式 DINO 仍為 r2 雙圖。</p>'
    write('folder-fix.html','來源資料夾 17 與 12 張核對',body)
    canvas=Image.new('RGB',(1000,1100),'#f4f7f8');d=ImageDraw.Draw(canvas)
    d.text((25,20),'這次達成：參照非螺絲，待測螺絲',font=font(31),fill='#173d4b')
    d.text((25,65),'同批 15 個正常對照無新增保留框；斜螺絲仍對取圖位置敏感。',font=font(22),fill='#173d4b')
    for row,n in enumerate([1,2]):
        y=115+row*475;d.text((25,y),'斜螺絲：本次判對，但稍微偏移仍會錯' if n==1 else '圓頭螺絲：本次判對，6 種小幅取圖變動也判對',font=font(25),fill='#173d4b')
        for col,(side,title) in enumerate([('reference','參照圖：DINO 判非螺絲'),('target','待測圖：DINO 判螺絲')]):
            d.text((25+col*490,y+40),title,font=font(22),fill='#173d4b');canvas.paste(Image.open(OUT/'images'/f'{n}-{side}-0.png').resize((400,400)),(25+col*490,y+75))
    canvas.save(OUT/'summary.png');print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':main()
