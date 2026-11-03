"""Readable three-way comparison, grouped inspection pages, no inference or production writes."""
import sys,json,math,os,html
from pathlib import Path
from collections import Counter
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.dino.full_paired_run import BASE,OUT,read
from experiments.full_dataset_review.readable_report import STYLE
esc=lambda x:html.escape(str(x))
NAV='<nav><a href="index.html">總結果</a><a href="good.html">良品誤報</a><a href="bad.html">不良品檢測</a><a href="checks.html">螺絲與誤報核對</a></nav>'
TYPES={'wire':'線材','edge':'板件邊界','component':'元件外觀','structure':'U 形結構','unknown':'待確認'}
def save(file,title,body):
    (OUT/file).write_text(f'<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><style>{STYLE}.result{{padding:12px;background:#edf5f5}}.pairimg{{width:100%;max-width:800px}}.state{{font-weight:bold}}details{{background:white;border:1px solid #dbe3e6;border-radius:8px;margin:18px 0;padding:16px}}nav{{display:flex;flex-wrap:wrap;gap:12px}}nav a{{margin:0}}.labels{{display:grid;grid-template-columns:1fr 1fr;text-align:center;font-weight:bold}}.muted{{overflow-wrap:anywhere}}[hidden]{{display:none!important}}</style>{body}</html>',encoding='utf-8')
def groups(items):
    gs=[]
    for z in sorted(items,key=lambda z:(z['c']['y'],z['c']['x'],z['name'])):
        c=z['c'];x,y=c['x']+c['w']/2,c['y']+c['h']/2
        g=next((g for g in gs if math.hypot(x-g[0]['c']['x']-g[0]['c']['w']/2,y-g[0]['c']['y']-g[0]['c']['h']/2)<=45),None)
        if g:g.append(z)
        else:gs.append([z])
    return sorted(gs,key=lambda g:-len(g))
def main():
    s=read(OUT/'summary.json');assert s['complete'];cases=read(OUT/'cases.json');rows=read(OUT/'rows.json');indexed={z['key']:z for z in cases}
    prior=read(ROOT/'workspace/dino-two-directions-20261103/visual-audit.json')
    audit_a={z['key']:z for z in prior['a']};audit_b={z['key']:z for z in prior['b']}
    oldtypes={f'{z["sha"]}-{z["id"]}':z['category'] for z in read(BASE/'grouped-review-index.json')['items']}
    for z in cases:
        key=z['key'];cat=oldtypes.get(key,'unknown');cat=cat if cat in TYPES and cat not in ('suspected',) else 'unknown'
        if key in audit_b or (key in audit_a and audit_a[key]['status']=='疑似新增螺絲會被誤刪'):cat='unknown'
        if z['known']:cat='unknown'
        z['category']=cat
    (OUT/'images').mkdir(exist_ok=True);(OUT/'photos').mkdir(exist_ok=True)
    # Generate only image extracts and overlays, reading each saved image once per photo.
    for i,r in enumerate(rows,1):
        zs=[z for z in cases if z['sha']==r['sha256']];p=BASE/'photos'/r['sha256']
        if not zs:continue
        with Image.open(p/'reference.png') as f:ref=f.convert('RGB')
        with Image.open(p/'aligned.png') as f:target=f.convert('RGB')
        for z in zs:
            file=OUT/'images'/(z['key']+'.jpg')
            if file.exists():continue
            c=z['c'];x,y,w,h=(c[k] for k in ('x','y','w','h'));side=max(120,w+48,h+48);x0=max(0,min(target.width-side,x+w//2-side//2));y0=max(0,min(target.height-side,y+h//2-side//2))
            canvas=Image.new('RGB',(800,400),'white')
            for j,im in enumerate([ref,target]):
                crop=im.crop((x0,y0,x0+side,y0+side));ImageDraw.Draw(crop).rectangle((x-x0,y-y0,x+w-x0,y+h-y0),outline='#e1263b',width=1);canvas.paste(crop.resize((400,400)),(j*400,0))
            canvas.save(file,quality=85)
        for outcome in [True,False]:
            image=target.copy();d=ImageDraw.Draw(image)
            for z in zs:
                if z['paired_keep']!=outcome:continue
                c=z['c'];x,y,w,h=(c[k] for k in ('x','y','w','h'));d.rectangle((x,y,x+w,y+h),outline='#e1263b',width=2);d.text((x,max(0,y-14)),str(z['id']),fill='#e1263b')
            image.thumbnail((1600,1600));image.save(OUT/'images'/(r['sha256']+('-kept.jpg' if outcome else '-removed.jpg')),quality=88)
        if i%40==0:print('REPORT IMAGES',i,'/',len(rows),flush=True)
    def category_file(z):return ('good' if z['label']=='OK' else 'bad')+'-'+z['machine']+'-'+z['category']+'.html'
    def card(z):
        state='保留' if z['paired_keep'] else '排除';why='待測像螺絲，參照不像。' if z['paired_keep'] else '兩邊都像螺絲，所以被雙圖規則排除。' if z['new_keep'] else '待測圖仍被 DINO 判成非螺絲。'
        machine_file=('good' if z['label']=='OK' else 'bad')+'-'+z['machine']+'.html'
        badge='；已有螺絲標記' if z['known'] else '；尚未逐框確認' if z['label']=='NG' else ''
        statuses=' → '.join(('保留' if z[k+'_keep'] else '排除') for k in ['old','new','paired'])
        return f'<article id="case-{z["key"]}"><h3>{esc(z["name"])} · 位置 {z["id"]}</h3><p class="state">本次：{state}。{why}</p><p>分類：{TYPES[z["category"]]}{badge} · <a href="{machine_file}">返回此機種</a> · <a href="{category_file(z)}#case-{z["key"]}">查看同類案例</a></p><details><summary>與舊版比較</summary><p>原版 → 只新增範例 → 新範例＋雙圖：<b>{statuses}</b></p></details><div class="labels"><span>正常參照圖</span><span>待測圖</span></div><img loading="lazy" class="pairimg" src="images/{z["key"]}.jpg"><p class="muted">紅框沿用原差分位置；保留不等於確認是螺絲。<a href="photos/{z["sha"]}.html">查看整張本次結果</a></p><details><summary>查看 DINO 比較依據</summary><p>分數是外觀相似度差值，不是正確率。參照：{z["reference"]["margin"]:.4f}；待測：{z["target"]["margin"]:.4f}。大於等於 0 判為螺絲。</p>'+''.join(f'<p>{side}最像的 3 張{lab}：{esc(", ".join(z[k]["evidence"][v]["neighbors"]))}</p>' for side,k in [('參照','reference'),('待測','target')] for lab,v in [('螺絲','screw'),('非螺絲','normal')])+'</details></article>'
    def gallery(zs):
        body=''
        for i,g in enumerate(groups(zs),1):
            # Prioritize newly excluded examples; show counts of all group members.
            g=sorted(g,key=lambda z:(not(z['new_keep'] and not z['paired_keep']),z['paired_keep'],z['name']))
            kept=sum(z['paired_keep'] for z in g)
            body+=f'<section><h3>相近位置 {i} · {len(g)} 框／{len({z["sha"] for z in g})} 張照片 · 保留 {kept}／排除 {len(g)-kept}</h3>'+card(g[0])
            if len(g)>1:body+=f'<details><summary>展開其餘 {len(g)-1} 個位置</summary>'+''.join(card(z) for z in g[1:])+'</details>'
            body+='</section>'
        return body
    # All photos, including zero-candidate images; new outcome, never the old overlay.
    for r in rows:
        zs=[z for z in cases if z['sha']==r['sha256']];keep=sum(z['paired_keep'] for z in zs)
        body=NAV+f'<h1>{esc(r["relative"])}</h1><p>差分 {len(zs)} 框；新範例＋雙圖保留 {keep} 框、排除 {len(zs)-keep} 框。</p>'
        machine_file='references.html' if r['is_reference'] else ('good' if r['label']=='OK' else 'bad')+'-'+r['machine']+'.html'
        cats=Counter(z['category'] for z in zs)
        category_links='、'.join(f'<a href="{("good" if r["label"]=="OK" else "bad")}-{r["machine"]}-{cat}.html">{TYPES[cat]} {count} 框</a>' for cat,count in cats.items()) or '無候選，無分類'
        body+=f'<div class="answer"><a href="{machine_file}">← 返回此機種 {r["machine"]}</a><p>本張分類（含已排除）：{category_links}</p></div>'
        ref_url=os.path.relpath(BASE/'photos'/r['sha256']/'reference.png',OUT).replace('\\','/')
        target_url=os.path.relpath(BASE/'photos'/r['sha256']/'aligned.png',OUT).replace('\\','/')
        body+=f'<details><summary>查看完整參照／待測圖</summary><div class="pair"><figure>參照圖<img loading="lazy" src="../{ref_url}"></figure><figure>待測圖<img loading="lazy" src="../{target_url}"></figure></div></details>'
        if zs:
            body+=f'<h2>本次保留位置</h2><a href="images/{r["sha256"]}-kept.jpg"><img src="images/{r["sha256"]}-kept.jpg"></a><details><summary>查看本次排除位置總圖</summary><img loading="lazy" src="images/{r["sha256"]}-removed.jpg"></details>'
            body+='<h2>保留框逐一看</h2>'+''.join(card(z) for z in zs if z['paired_keep'])
            body+=f'<details><summary>查看被排除的 {len(zs)-keep} 框</summary>'+''.join(card(z) for z in zs if not z['paired_keep'])+'</details>'
        else:body+='<p>此照片原有差分未提出候選，DINO 沒有執行。不能把不良品零候選視為正確檢出。</p>'
        oldlink=os.path.relpath(BASE/'photos'/r['sha256']/'report.html',OUT/'photos').replace('\\','/')
        body+=f'<p><a href="{oldlink}">原始完整照片與舊版紀錄 →</a></p>'
        # Content built for root; photo pages sit one directory deeper.
        body=body.replace('href="index.html"','href="../index.html"').replace('href="good.html"','href="../good.html"').replace('href="bad.html"','href="../bad.html"').replace('href="checks.html"','href="../checks.html"').replace('src="images/','src="../images/').replace('href="images/','href="../images/').replace('href="photos/','href="').replace('href="good-','href="../good-').replace('href="bad-','href="../bad-').replace('href="references.html"','href="../references.html"')
        save('photos/'+r['sha256']+'.html',r['relative'],body)
    for label,stem,title in [('OK','good','良品誤報'),('NG','bad','不良品檢測')]:
        rs=[r for r in rows if r['label']==label and not r['is_reference']];zs=[z for z in cases if z['label']==label]
        body=NAV+f'<h1>{title}</h1><p>本次使用 47＋65 範例，並加看參照圖。先選機種，再看外觀類型與相近位置。</p>'
        if label=='NG':body+='<p><b>不良品的保留框數不是螺絲顆數；排除框也不代表刪對。</b></p>'
        body+='<table><tr><th>機種</th><th>照片</th><th>差分框</th><th>本次排除</th><th>本次保留</th></tr>'
        for machine in sorted({r['machine'] for r in rs},key=lambda m:({'MPT10':0,'MPT12':1,'KPH33':2,'MPT11':3}.get(m,9),m)):
            subset=[z for z in zs if z['machine']==machine];mr=[r for r in rs if r['machine']==machine];file=f'{stem}-{machine}.html'
            body+=f'<tr><td><a href="{file}">{machine} →</a></td><td>{len(mr)}</td>'+f'<td>{len(subset)}</td><td>{sum(not z["paired_keep"] for z in subset)}</td><td>{sum(z["paired_keep"] for z in subset)}</td></tr>'
            overview=NAV+f'<h1>{machine}：{title}</h1><p>依外觀分組；沿用原先人工或自動分類，未確認類型會明確標示。</p>'
            for cat in TYPES:
                cc=[z for z in subset if z['category']==cat]
                cf=f'{stem}-{machine}-{cat}.html';keep=sum(z['paired_keep'] for z in cc)
                overview+=f'<article><h2><a href="{cf}">{TYPES[cat]} →</a></h2><p>{len(cc)} 框；本次保留 {keep}、排除 {len(cc)-keep}。</p></article>'
                save(cf,TYPES[cat],NAV+f'<p><a href="{file}">← 返回 {machine}</a></p><h1>{machine} / {TYPES[cat]}</h1><p>45 像素內的相近位置放同組，僅供瀏覽，不保證是同一物件。</p>'+('<p>目前沒有已分類至此類的候選。</p>' if not cc else '<button onclick="document.querySelectorAll(\'details\').forEach(d=>d.open=true)">展開全部同類照片</button> '+gallery(cc)))
            overview+='<h2>全部照片（包含零候選照片）</h2><table><tr><th>照片</th><th>分類</th><th>保留</th><th>排除</th></tr>'
            for r in mr:
                cc=[z for z in subset if z['sha']==r['sha256']];keep=sum(z['paired_keep'] for z in cc)
                cats=Counter(z['category'] for z in cc);ct='、'.join(f'<a href="{stem}-{machine}-{cat}.html">{TYPES[cat]} {n}</a>' for cat,n in cats.items()) or '無候選'
                overview+=f'<tr><td><a href="photos/{r["sha256"]}.html">{esc(Path(r["name"] if "name" in r else r["relative"]).name)}</a></td><td>{ct}</td><td>{keep}</td><td>{len(cc)-keep}</td></tr>'
            save(file,machine+' '+title,overview+'</table>')
        save(stem+'.html',title,body+'</table>')
    # Keep annotated positives and visual suspicions separate, and freeze earlier audit groups.
    checkgroups=[('已標記螺絲（2 處）',[z for z in cases if z['known']]),('前次疑似誤刪（14 處，尚非完整標準答案）',[indexed[k] for k in audit_b if not indexed[k]['known']]),
                 ('圖一：前次目視原有結構（58 框）',[indexed[k] for k,v in audit_a.items() if v['status']=='原有物件／線材變化']),
                 ('圖一：前次疑似新增螺絲風險（9 框）',[indexed[k] for k,v in audit_a.items() if v['status']=='疑似新增螺絲會被誤刪']),
                 ('圖一：前次未確定（7 框）',[indexed[k] for k,v in audit_a.items() if v['status']=='暫時無法確定'])]
    checks=NAV+'<h1>先核對：有沒有保住螺絲、減少誤報？</h1><p>沿用先前固定核對位置；沒有因為新模型結果改掉標籤。新範例與這批照片可能重複，以下只作開發比較。</p>';metrics=[]
    for title,zs in checkgroups:
        counts={k:sum(z[k+'_keep'] for z in zs) for k in ['old','new','paired']};metrics.append(dict(title=title,total=len(zs),**counts))
        checks+=f'<section><h2>{title}</h2><p>保留數：原版 {counts["old"]} → 只新增範例 {counts["new"]} → 新範例＋雙圖 {counts["paired"]}。</p><details><summary>展開本組證據圖片</summary>'+gallery(zs)+'</details></section>'
    save('checks.html','螺絲與誤報核對',checks)
    (OUT/'checks-summary.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf-8')
    known=metrics[0];suspected=metrics[1];existing=metrics[2];risk=metrics[3]
    body=NAV+'<h1>新範例＋參照圖：這次測試結果</h1><p>兩個條件都在本次離線測試啟用：47 張螺絲＋65 張非螺絲，各取最像 3 張；同時判斷參照與待測小圖。</p>'
    body+=f'<div class="answer"><b>先看結論：新增範例有幫助；目前的雙圖刪除規則仍會誤刪，不宜直接套用。</b><p>良品維持零誤報。新增範例救回了本批 2 處已標記螺絲；雙圖規則可消除既有結構誤報，但也把先前 {risk["total"]} 個新增疑似螺絲風險框中的 {risk["new"]-risk["paired"]} 個刪掉。</p><p class="muted">這是開發測試。新範例可能與本批圖資重複，不能把本次結果當成新照片上的準確率。</p></div>'
    body+=f'<div class="answer"><h2>圖二：原本漏掉的螺絲有沒有留下？</h2><p>2 處已有目視標記：原版保留 {known["old"]} 處，新增範例後 {known["new"]} 處，加看參照圖後 {known["paired"]} 處。</p><p>另 14 處疑似誤刪：保留 {suspected["old"]} → {suspected["new"]} → {suspected["paired"]} 處。這組仍待確認，不能當成準確率。</p></div>'
    body+=f'<div class="answer"><h2>圖一：原本就有的物件，有沒有少報？</h2><p>先前目視屬原有結構的 58 框：原版保留 {existing["old"]}，新增範例後 {existing["new"]}，加看參照圖後剩 {existing["paired"]}。</p><p><b>代價也要看：</b>先前 9 個新增疑似螺絲風險框，新增範例後保留 {risk["new"]}，加看參照圖後保留 {risk["paired"]}。</p><a href="checks.html">查看這些固定位置的證據 →</a></div>'
    anchors=[z for z in cases if (z['name']=='MPT11/NG/1.png' and z['id']==7) or (z['name'].endswith('17_13_17_96.tiff') and z['id']==80)]
    body+='<details><summary>直接看你最初指出的圖一、圖二，本次各變成什麼結果</summary>'+''.join(card(z) for z in anchors)+'</details>'
    body+='<h2>全部圖資比較</h2><table><tr><th>項目</th><th>原版 31＋65</th><th>新範例 47＋65</th><th>新範例＋雙圖</th></tr>'
    for title,label,field in [('良品留下的誤報框','OK','kept'),('良品沒有誤報的照片','OK','zero_images'),('不良品保留框（不是螺絲顆數）','NG','kept'),('不良品零候選照片（不能當作成功）','NG','zero_images')]:
        body+='<tr><td>'+title+'</td>'+''.join(f'<td>{s[label][k][field]}</td>' for k in ['old','new','paired'])+'</tr>'
    body+='</table><p>139 張良品、47 張不良品；另 4 張正常參照自比不計入成效。全部沿用同一批 2793 個差分候選。本次只重算 AI，未改候選位置或取圖方式。</p><p><a href="good.html">查看良品誤報 →</a>　<a href="bad.html">查看不良品保留與排除 →</a></p><details><summary>這次採用的雙圖規則與限制</summary><p>待測像螺絲、參照不像 → 保留；兩邊都像 → 排除；待測不像 → 排除。這是本次測試規則，尚未證明兩邊是同一物件。</p><p>16 張新範例來自使用者提供的現場拼圖，可能與本批照片重複，來源未完整對應，不能宣稱是獨立測試準確率。42 張良品曾提供正常範例。既有 #52 的標記疑義未被當成正確螺絲納入以上成效。</p><p>正式 active.json 沒有更動。任何保留／排除都保存在此次獨立結果中，舊報告和人工紀錄不變。</p><a href="plan.json">執行設定與輸入雜湊</a> · <a href="summary.json">完整數據</a></details>'
    save('comparison.html','版本差異比較（附加）',body)
    from experiments.dino.full_review_home import build_home
    build_home(cases,rows,s,save,NAV,TYPES)
    (OUT/'review-index.json').write_text(json.dumps([dict(key=z['key'],sha=z['sha'],id=z['id'],category=z['category'],machine=z['machine'],label=z['label'],kept=z['paired_keep']) for z in cases],ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(metrics,ensure_ascii=False),flush=True);print('REPORT COMPLETE',len(list(OUT.glob('*.html')))+len(list((OUT/'photos').glob('*.html'))),flush=True)
if __name__=='__main__':main()
