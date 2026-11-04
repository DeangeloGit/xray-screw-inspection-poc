"""Plain Chinese readout of the fixed 17-case experiment, including all failures."""
import sys,html,json
from pathlib import Path
from collections import Counter
from PIL import Image,ImageDraw,ImageOps
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.dino.local_added_object_pilot import OUT,read,save,digest,font

NAMES={
 'new_alert':'提醒：可能新增物件','movement_hint':'較像移動／明暗變化','explained':'差異已能解釋','uncertain':'分不清，保留確認',
 'similar_found':'附近找到相似外觀','no_similar_found':'附近找不到相似外觀',
 'similar':'兩圖外觀相近','different':'提醒：兩圖外觀差很多'}
NOTES={
 1:'待測圖多了斜螺絲。直接比較 DINO 外觀仍分不清；單靠像素差異也分不清。附近找輪廓可以提醒，但同一方法會誤報正常線材，所以還不能當成解法。',
 2:'待測圖多了圓頭螺絲。直接比較 DINO 外觀、像素差異都會提醒；但「差很多」只證明有變化，還不是模型認出這是一顆螺絲。',
 3:'兩圖原本都有圓形物件，待測圖同時有明暗、線材與外觀大小差異。三種補充比較都分不清；現行 r2 在此處原本就有正確排除，不能把本次分不清說成改善。',
 4:'線材位置改變。直接比較 DINO 分不清；附近找輪廓也找不到夠像的片段，會造成正常案例的誤報。',
 5:'同一帶線材左右移動；直接比較 DINO 仍覺得兩圖相近。這是有幫助的正常對照。',
 6:'線材在兩圖的位置不同，局部小圖可能只看到移入、沒看到原來線材的位置。只看新增深色區域會誤報；較大範圍對照才能看出線材移動。',
 7:'線材弧度改變，但兩圖仍有同類線材外觀；直接比較 DINO 覺得相近。',
 8:'線材位置／外觀改變，直接比較 DINO 分不清。不能把它計為已成功排除。',
 9:'線材彎曲位置改變；直接比較 DINO 覺得相近，附近也找到相似外觀。',
 10:'線材彎曲改變，附近找輪廓找不到夠像的片段，會誤報；DINO 直接比較仍分不清。',
 11:'線束外觀與位置變化較多，直接比較 DINO 分不清。',
 12:'良品板件邊界外觀有差異。附近找輪廓能找到很像的邊界，但單看新增深色區域會誤報。',
 13:'另一處良品板件邊界。附近找輪廓能對上，直接比較 DINO 仍分不清。',
 14:'良品元件區域的外觀／明暗有變化；三種比較都未形成明確的原有物件判斷。',
 15:'這是良品資料夾的正常元件案例，卻被 DINO 直接比較判成「差很多」。它是不能只用兩圖相似程度決定新增螺絲的反例。',
 16:'U 形結構在兩圖位置不同；附近找輪廓和 DINO 直接比較都能找到相似外觀。',
 17:'另一機種的 U 形結構移動，兩種外觀比較也都找到相似外觀。'}
CSS='''body{font:18px/1.7 "Microsoft JhengHei",sans-serif;color:#173d4b;background:#f4f7f8;margin:0}main{max-width:1180px;margin:auto;padding:28px}h1{font-size:30px}h2{font-size:25px}h3{font-size:21px}a{color:#008694}nav a{margin-right:22px}article,section,.answer{background:white;border:1px solid #d9e3e7;border-radius:10px;padding:22px;margin:22px 0}.answer{border-left:6px solid #00838c}table{border-collapse:collapse;width:100%;background:white}td,th{border:1px solid #d5e2e5;padding:12px;text-align:left}th{background:#e8f0f3}img{max-width:100%;height:auto}summary{cursor:pointer;color:#00838c;padding:12px}small,.note{color:#536c78}.bad{color:#b22c37}.ok{color:#087767}.badge{background:#edf4f6;padding:5px 10px;border-radius:6px}.pair{width:100%;max-width:950px}.tiles{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}.tiles img{width:224px}button{font:inherit;padding:10px}figure{margin:0}'''
NAV='<nav><a href="index.html">先看結果</a><a href="normal.html">正常案例分類對照</a><a href="details.html">全部數據與方法</a></nav>'
def write(name,title,body):
    (OUT/name).write_text('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+title+'</title><style>'+CSS+'</style><main>'+NAV+body+'</main></html>',encoding='utf-8')

def main():
    plan=read(OUT/'plan.json');cases=plan['cases'];v1=read(OUT/'results-v1.json');v2=read(OUT/'results-v2.json');v3=read(OUT/'results-v3.json')
    assert len(cases)==len(v1)==len(v2)==len(v3)==17
    for i,z in enumerate(cases):
        assert all(v[i]['key']==z['key'] for v in [v1,v2,v3])
        # Reproduce saved r2 decisions exactly, retaining its 47+65 example bank.
        r2=v3[i]['target']['label']=='screw' and v3[i]['reference']['label']!='screw'
        assert r2==z['paired_keep']
    counts={name:{kind:dict(Counter(v[i]['outcome'] for i,z in enumerate(cases) if z['expected']==kind)) for kind in ['new','normal']} for name,v in [('pixel',v1),('nearby',v2),('dino_direct',v3)]}
    save(OUT/'summary.json',dict(candidates=17,positive_candidates=2,positive_photos=1,normal_candidates=15,wire_candidates=8,other_normal_candidates=7,counts=counts,production_changed=False,full_dataset_rerun=False,conclusion='尚不能同時穩定辨認兩顆新增螺絲並排除正常變化；不可套用正式流程',not_accuracy_estimate=True))
    # Render unmodified reference/target contexts with identical crops and red boxes.
    for n,z in enumerate(cases,1):
        c=z['c'];cx,cy=c['x']+c['w']/2,c['y']+c['h']/2;side=max(100,c['w']+64,c['h']+64)
        box=(round(cx-side/2),round(cy-side/2),round(cx+side/2),round(cy+side/2))
        canvas=Image.new('RGB',(950,505),'white');d=ImageDraw.Draw(canvas)
        for j,(f,label) in enumerate([('reference.png','正常參照圖：相同位置'),('aligned.png','待測圖：相同位置')]):
            im=Image.open(Path(z['source'])/f).convert('RGB').crop(box)
            draw=ImageDraw.Draw(im);draw.rectangle((c['x']-box[0],c['y']-box[1],c['x']+c['w']-box[0],c['y']+c['h']-box[1]),outline='#eb334e',width=1)
            canvas.paste(im.resize((450,450)),(j*480,45));d.text((j*480,3),label,font=font(24),fill='#173d4b')
        canvas.save(OUT/'images'/f'{n}-pair.jpg',quality=94)

    def card(n):
        z=cases[n-1];a,b,c=(v[n-1] for v in [v1,v2,v3]);p=Path(z['source']);name=html.escape(z['name'])
        return f'''<article id="case-{n}"><h3>{n}. {html.escape(z['title'])} · 位置 {z['id']}</h3><p><span class="badge">{z['machine']}／{z['category']}</span>　現行 r2：{'保留' if z['paired_keep'] else '排除'}</p><p><b>{NOTES[n]}</b></p><img class="pair" loading="lazy" src="images/{n}-pair.jpg" alt="案例 {n} 正常參照與待測同位置對照"><p class="note">紅框沿用原差分框；這裡顯示較大範圍方便你看懂，沒有修改正式裁圖或檢測框。</p><p><b>本次直接比較 DINO 兩圖：</b>{NAMES[c['outcome']]}。</p><details><summary>查看 DINO 實際小圖、另外兩種測法與數據</summary><div class="tiles"><figure><figcaption>DINO 的參照小圖</figcaption><img src="images/{n}-dino-reference.png"></figure><figure><figcaption>DINO 的待測小圖</figcaption><img src="images/{n}-dino-target.png"></figure></div><table><tr><th>測法</th><th>結果</th></tr><tr><td>直接比較 DINO 兩圖外觀</td><td>{NAMES[c['outcome']]}；相似分數 {c['similarity']:.3f}（不是螺絲機率）</td></tr><tr><td>先對齊、調整明暗，再看新增深色區域</td><td>{NAMES[a['outcome']]}</td></tr><tr><td>到參照圖附近找相似輪廓</td><td>{NAMES[b['outcome']]}；相似分數 {b['correlation']:.3f}</td></tr></table><p>附近找到的最相似片段如下；即使有圖也不代表找到同一物件，必須看上面的分數及結果。</p><img src="images/{n}-appearance-match.png" style="width:224px;image-rendering:auto"></details><p class="note">來源：{name}；{html.escape(z['basis'])}。</p><p><a href="{(p/'reference.png').as_uri()}">完整參照圖</a> · <a href="{(p/'aligned.png').as_uri()}">完整待測圖</a> · <a href="normal.html#machine-{z['machine']}">返回此機種</a> · <a href="normal.html#category-{z['machine']}-{z['category']}">查看同類案例</a></p></article>'''

    intro='''<h1>兩組新增螺絲：這次能分出來嗎？</h1><div class="answer"><h2>還不能穩定分開，所以先不套用。</h2><p>你指出的兩顆確實是新增螺絲；本次測的是程式能不能辨認這個差別。</p><p><b>圓頭螺絲：</b>兩種補充比較能提醒「有明顯變化」。<br><b>斜螺絲：</b>DINO 直接比較仍分不清；另外找輪廓雖能提醒，卻也誤報正常線材。</p><p>目前沒有一種測法能同時把兩顆分清楚，又不增加正常案例的誤報。</p></div><p>固定小實驗：<b>2 個新增螺絲位置＋15 個正常對照</b>（8 個線材、7 個原有物件／板件）。先選案例、再計算；成功、失敗與分不清的全部列出。兩顆螺絲來自同一張照片，不是整批準確率。</p><h2>先看你指定的兩顆</h2><table><tr><th>案例</th><th>現行 r2</th><th>本次直接比較 DINO 兩圖</th></tr><tr><td>斜螺絲 #94</td><td class="bad">排除（誤刪）</td><td>分不清，應保留確認</td></tr><tr><td>圓頭螺絲 #34</td><td class="bad">排除（誤刪）</td><td>能提醒兩圖有明顯差別</td></tr></table><p>「能提醒」不是已認出螺絲；「分不清」也不算辨識成功。這些是離線結果，正式程式仍維持原版本。</p>'''
    body=intro+card(1)+card(2)+'''<h2>那正常線材、原有物件呢？</h2><p>以「直接比較 DINO 兩圖」這項來看：</p><table><tr><th>15 個正常對照</th><th>數量</th><th>代表什麼</th></tr><tr><td>兩圖外觀相近</td><td>5</td><td>有助於判斷是原有物件；尚不能單憑此項自動刪除。</td></tr><tr><td>分不清</td><td>9</td><td>仍需要保留確認，不能算成功排除。</td></tr><tr><td class="bad">誤當成明顯變化</td><td>1</td><td>正常元件仍可能被誤報。</td></tr></table><p><a href="normal.html">看全部正常案例：機種 → 類型 → 位置 →</a></p><h2>這次最重要的發現</h2><p><b>「兩張小圖不一樣」不能直接等於「新增螺絲」。</b>線材移動、板件明暗改變，也會讓兩張小圖差很多；反過來，背景很像也會掩蓋新增螺絲。</p><p>這批資料甚至出現：斜螺絲兩圖的相似分數，比原本就有的圓形物件還高。因此單純換一個門檻，無法同時處理好這兩例。</p><p><b>下一個值得測的方向：</b>把新增物件與周圍背景分開比較，並在較大範圍追查線材原來的位置；同時保留這 17 個案例當固定檢查題。這是後續建議，本次尚未實作，也不先套用正式流程。</p><details><summary>另外兩種測法也試過：看完整數字</summary>'''
    trial_table='''<table><tr><th>補充測法</th><th>2 個新增螺絲</th><th>15 個正常對照</th></tr><tr><td>直接比較 DINO 外觀</td><td>1 提醒／1 分不清</td><td>5 相近／9 分不清／1 誤報</td></tr><tr><td>對齊與調整明暗後，找新增深色區塊</td><td>1 提醒／1 分不清</td><td>11 較像移動／1 分不清／3 誤報</td></tr><tr><td>到參照圖附近找相似輪廓</td><td>1 提醒／1 分不清</td><td>6 找到相似外觀／6 分不清／3 誤報</td></tr></table><p>三種獨立測法，沒有合併後挑最好結果。所有「較像移動／相近」都只是比較線索，尚未證明足以安全自動排除。</p>'''
    body+=trial_table+'</details><p class="note">未改正式流程、模型、47＋65 範例、雙圖設定、人工紀錄；未重跑整批差分。正式 r2 判斷由既有小圖結果重現核對。</p>'
    body=body.replace('normal.html#category-MPT12-新增螺絲','index.html#case-1')
    body+='<p class="note">本報告「誤報」是補充測法對正常案例提出錯誤提醒；不是正式程式新增的誤報。試驗中的「分不清」保留人工確認，不自動刪除。</p>'
    write('index.html','新增螺絲與正常變化：小實驗結果',body)

    cats=['線材','板件邊界','元件外觀','U 形結構','待確認']
    body='<h1>正常案例：全部 15 個都列出</h1><p>14 個來自既有良品資料夾，另 1 個是你先前圖一指出的原有圓形物件。外觀分類是目視整理；良品標記不等於已證明每一處變化的物理原因。</p>'
    for machine in ['MPT10','MPT11','MPT12','KPH33']:
        ns=[n for n,z in enumerate(cases,1) if z['expected']=='normal' and z['machine']==machine]
        body+=f'<section id="machine-{machine}"><h2>{machine} · {len(ns)} 個正常對照</h2>'
        for cat in cats:
            sub=[n for n in ns if cases[n-1]['category']==cat]
            body+=f'<div id="category-{machine}-{cat}"><h3>{cat} · {len(sub)} 個位置</h3>'
            if sub:
                body+=card(sub[0])
                if len(sub)>1:body+=f'<details><summary>展開其餘 {len(sub)-1} 個同類位置（每個位置各 1 個案例）</summary>'+''.join(card(n) for n in sub[1:])+'</details>'
            else:body+='<p class="note">本次固定小樣本未選入；不是整批沒有案例。</p>'
            body+='</div>'
        body+='</section>'
    # Opening an anchor also opens all details parents.
    body+='<script>const n=document.getElementById(decodeURIComponent(location.hash.slice(1)));for(let p=n;p;p=p.parentElement)if(p.tagName==="DETAILS")p.open=true;if(n)n.scrollIntoView();</script>'
    write('normal.html','正常對照：機種與類型',body)
    body='<h1>完整數據與可重現方法</h1>'+trial_table+'''<h2>本次實際改了什麼？</h2><p>只新增獨立實驗腳本與報告。DINO 權重、47 張螺絲＋65 張正常範例、正式雙圖規則全部沿用。直接比較 DINO 外觀是實驗讀出方式，不是重訓或新模型。</p><p>沿用既有候選框及原本向外 12 像素的小圖。DINO 仍依正式做法縮放、取中央正方形；輪廓搜尋則保留完整長方形小圖，搜尋參照位置附近 32 像素。報告大圖只是方便看完整背景。</p><h2>三種測法的固定規則</h2><ol><li>像素差異：用候選外圍對齊、估算明暗，候選與外加 12 像素不參與估計。比對可信且新增深色區域占變化量至少 80%、接觸候選的連通區至少 12 像素，才提出提醒；正反變化接近則只列移動線索。</li><li>附近輪廓：參照小圖附近 32 像素搜尋。相似分數至少 0.75 且未碰搜尋邊界，才列相似；低於 0.45 列找不到，中間列分不清。相似不證明就是同一件實物。</li><li>DINO 直接外觀：用既有模型產生的兩圖外觀向量直接比較。至少 0.80 列相近，低於 0.60 提醒差很多，中間列分不清。分數不是機率。</li></ol><p>這些是探索用門檻，各輪執行前寫入獨立規則檔；沒有在看完分數後調整。尚未經其他照片獨立驗證，不能當成正式安全刪除標準。第一、二輪有失敗，第三輪改用 DINO 直接比較；三輪都完整公開。</p><h2>逐例數字</h2><table><tr><th>例</th><th>預期／類型</th><th>目前 r2</th><th>DINO 直接相似度</th><th>本輪結果</th></tr>'''
    for n,z in enumerate(cases,1):
        link=('index.html' if n<=2 else 'normal.html')+f'#case-{n}'
        body+=f'<tr><td><a href="{link}">{n} · {z["machine"]} #{z["id"]}</a></td><td>{z["category"]}</td><td>{"保留" if z["paired_keep"] else "排除"}</td><td>{v3[n-1]["similarity"]:.4f}</td><td>{NAMES[v3[n-1]["outcome"]]}</td></tr>'
    body+='</table><p><a href="plan.json">固定案例與來源雜湊</a> · <a href="summary.json">統計</a> · <a href="results-v1.json">像素比較原始結果</a> · <a href="results-v2.json">附近輪廓原始結果</a> · <a href="results-v3.json">DINO 原始結果</a> · <a href="preservation.json">檔案保留核對</a></p>'
    write('details.html','小實驗方法與完整數據',body)
    # Portable visual summary for direct display in the chat.
    canvas=Image.new('RGB',(1000,1300),'#f4f7f8');d=ImageDraw.Draw(canvas)
    d.text((25,20),'這次小實驗：還不能穩定分開',font=font(32),fill='#173d4b')
    for j,n in enumerate([1,2]):
        y=85+j*575
        title='斜螺絲：DINO 直接比較仍分不清' if n==1 else '圓頭螺絲：能提醒有差別，但還不是認出螺絲'
        d.text((25,y),title,font=font(26),fill='#173d4b')
        canvas.paste(Image.open(OUT/'images'/f'{n}-pair.jpg'),(25,y+45))
    d.text((25,1240),'正常對照 15 個：5 相近、9 分不清、1 誤報。正式程式未修改。',font=font(23),fill='#173d4b')
    canvas.save(OUT/'summary.png')
    assert all(digest(Path(p))==v for p,v in plan['hashes'].items())
    save(OUT/'preservation.json',dict(verified_files=len(plan['hashes']),unchanged=True,all_17_r2_decisions_reproduced=True,production_changes=False))
    print(json.dumps(counts,ensure_ascii=False))

if __name__=='__main__':main()
