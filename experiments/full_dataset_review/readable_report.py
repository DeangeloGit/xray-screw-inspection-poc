"""Decision-first review pages; keep technical details available separately."""
import json,html,shutil
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]/'workspace/windows-check/diagnostics/v10-full-evaluation-20261103'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def esc(v):return html.escape(str(v))
STYLE='''body{max-width:1120px;margin:36px auto;padding:0 20px;font:18px/1.75 "Microsoft JhengHei",sans-serif;color:#183c45;background:#f6f8f9}h1{font-size:30px}h2{font-size:23px;margin-top:30px}a{color:#007b85}nav a{margin-right:20px}.answer{background:#fff;border-left:5px solid #007b85;padding:18px 24px;margin:24px 0}table{border-collapse:collapse;background:white;width:100%}td,th{padding:12px;border:1px solid #dbe3e6;text-align:left}th{background:#eaf1f3}article{background:white;border:1px solid #dbe3e6;border-radius:10px;padding:20px;margin:22px 0}img{max-width:100%;height:auto}.pair,.triple{display:grid;gap:16px;grid-template-columns:repeat(2,minmax(0,1fr))}.triple{grid-template-columns:repeat(3,minmax(0,1fr))}svg{width:100%;height:auto}.muted{color:#667b82;font-size:15px}summary{cursor:pointer}input,select{font:inherit;padding:8px}.controls{padding:12px 0}tr[hidden]{display:none}@media(max-width:800px){.triple{grid-template-columns:1fr}table{font-size:14px}td,th{padding:7px}}'''
NAV='<nav><a href="index.html">先看結論</a><a href="good.html">良品：哪些地方多框了</a><a href="bad.html">不良品：框到哪裡</a></nav>'
def page(title,body,script=''):
    return f'<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><style>{STYLE}</style>{body}<script>{script}</script></html>'
def save(path,text):
    archive=path.with_name('technical.html' if path.name=='report.html' else 'technical-'+path.name)
    if path.exists() and not archive.exists():shutil.copyfile(path,archive)
    path.write_text(text,encoding='utf-8')

def table(rows,good=False):
    body='<div class="controls"><input id="search" placeholder="輸入機種或檔名搜尋"></div><table><thead><tr><th>照片</th><th>'+('多框幾個位置' if good else '算法框出幾個位置')+'</th><th>'+('查看結果' if good else '真正螺絲的核對進度')+'</th></tr></thead><tbody>'
    for row in rows:
        href='photos/'+row['sha256']+'/report.html'
        checks=read(ROOT/'photos'/row['sha256']/'known-check.json') if row['success'] else []
        status=('沒有誤報' if row['count']==0 else '查看這些誤報') if good else ('既有 1 處目視標記有框到；其餘未核對' if checks and all(c['matched_ids'] for c in checks) else '尚未逐一核對螺絲位置')
        body+=f'<tr data-search="{esc(row["relative"].lower())}"><td>{esc(row["relative"])}</td><td>{row.get("count","分析失敗")}</td><td><a href="{href}">{status} →</a></td></tr>'
    return body+'</tbody></table>'
FILTER="document.getElementById('search').oninput=e=>{for(const r of document.querySelectorAll('tbody tr'))r.hidden=!r.dataset.search.includes(e.target.value.toLowerCase().trim())};"

def main():
    rows=read(ROOT/'results.json');summary=read(ROOT/'summary.json');plan=read(ROOT/'plan.json')
    assert len(rows)==190 and summary['complete']
    tested=[r for r in rows if not r['is_reference']]
    good=[r for r in tested if r['label']=='OK'];bad=[r for r in tested if r['label']=='NG']
    # The user supplied these as good images: a proposed defect region is a false alarm.
    top=NAV+'<h1>這版做得如何？</h1><div class="answer"><b>我的結論：目前還不能交付「已驗收定案」的結論。</b><p>良品的誤報已統計清楚；不良品是否把真正螺絲找齊，我沒有完成逐一核對。上一份把跑完程式當成驗收報告，是我交付不完整。</p></div>'
    top+='<h2>1. 良品：目前仍會多框位置</h2><p>你提供的良品，理想結果是沒有框。這裡把所有多出的框都算誤報，紅框與黃框不分開抵銷。</p><table><tr><th>機種</th><th>測試良品</th><th>沒有誤報</th><th>有誤報</th><th>誤報框總數</th></tr>'
    for machine in ['MPT10','MPT12','KPH33']:
        m=summary['groups'][machine+'/OK']
        top+=f'<tr><td>{machine}</td><td>{m["images"]} 張</td><td>{m["zero"]} 張</td><td>{m["positive"]} 張</td><td>{m["candidates"]} 個</td></tr>'
    top+='<tr><th>合計</th><th>139 張</th><th>55 張</th><th>84 張</th><th>128 個</th></tr></table><p><a href="good.html">看這 128 個誤報在哪裡 →</a></p>'
    top+='<h2>2. 不良品：程式跑完了，但漏檢核對還沒做完</h2><p>MPT11 的 47 張不良品共框出 2,665 個位置。<b>這個數字只是框數，不是抓到 2,665 顆螺絲，也不能拿來證明沒有漏檢。</b></p><p>目前能對照既有目視標記確認的，是 <b>5.png、9.png 各 1 處螺絲都有框到</b>。其他照片、以及這兩張裡的其他物體，我尚未逐一核對。這是我還沒完成的工作，不是要你從一堆警語中自行猜測結果。</p><p><a href="bad.html">逐張看不良品框到了哪裡 →</a></p>'
    top+='<h2>3. 下一步應驗收什麼</h2><p>要回答能否定案，還欠一張明確清單：每張 NG 的螺絲位置、哪些有框到、哪些漏掉。這份報告先把已完成的誤報統計與尚未完成的螺絲核對分清楚。</p>'
    top+='<details><summary>測試範圍與原始技術資料</summary><p>共 190 張；4 張作為各機種參照，剩下 139 張良品、47 張不良品用來測試。演算法 V10、門檻 0.13，每個機種只用一張參照圖。MPT11 的唯一良品已作參照，沒有另張良品可計誤報。CLIP 沒有刪除任何框。</p><p>MPT12 這次包含舊參照作為待測，多出 4 個框，所以是 60 個；前次共同 48 張的 56 個框沒有改變。</p><a href="technical-index.html">原始技術統計</a> · <a href="plan.json">參照圖與執行設定</a></details>'
    save(ROOT/'index.html',page('V10 驗收進度與結果',top))
    good.sort(key=lambda r:(-r.get('count',0),r['relative']))
    bad.sort(key=lambda r:r['relative'])
    save(ROOT/'good.html',page('良品誤報清單',NAV+'<h1>良品：哪些地方多框了？</h1><p><b>139 張良品：55 張沒有框，84 張有誤報，共 128 個框。</b></p><p>依你提供的良品標籤統計。下表按框數由多到少排列，點開可看每個位置的參照圖與待測圖。</p>'+table(good,True),FILTER))
    save(ROOT/'bad.html',page('不良品檢查進度',NAV+'<h1>不良品：框到了哪裡？</h1><p><b>47 張已完成程式分析；真正螺絲是否找齊，尚未完成逐一核對。</b></p><p>「框數」只是這張圖產生的標記數。下表另外列出我實際完成的螺絲核對進度，不把兩件事混在一起。</p>'+table(bad),FILTER))
    for row in rows:
        folder=ROOT/'photos'/row['sha256'];r=read(folder/'result.json')
        with Image.open(folder/'aligned.png') as im:width,height=im.size
        heading='參照圖自比' if row['is_reference'] else '良品誤報檢查' if row['label']=='OK' else '不良品標記檢查'
        body='<nav><a href="../../index.html">回到結論</a><a href="../../good.html">良品清單</a><a href="../../bad.html">不良品清單</a></nav>'
        body+=f'<h1>{heading}：{esc(Path(row["path"]).name)}</h1><p>{row["machine"]} · 參照圖：{esc(Path(row["reference"]).name)}</p>'
        if row['is_reference']:body+='<p>這張是參照圖本身，不計入測試成效。</p>'
        elif row['label']=='OK':body+=f'<div class="answer">你提供的分類是良品。算法多框了 <b>{r["proposal_count"]} 個位置</b>，下方逐個列出。</div>'
        else:
            known=read(folder/'known-check.json')
            state='既有 1 處目視標記有框到；其他位置尚未逐一核對。' if known and all(c['matched_ids'] for c in known) else '我尚未逐一核對這張圖真正的螺絲位置。'
            body+=f'<div class="answer">你提供的分類是不良品。算法框出 <b>{r["proposal_count"]} 個位置</b>。<br>{state}</div>'
        body+='<p>三圖方向相同。紅色是優先查看、黃色是其他標記；兩種顏色都保留在下方清單。</p><div class="triple">'
        for label,file in [('參照圖','reference.png'),('待測圖','aligned.png'),('算法標記','aligned_overlay.png')]:body+=f'<div><b>{label}</b><a href="{file}"><img src="{file}"></a></div>'
        body+='</div><h2>逐個位置對照</h2>'
        if not r['candidates']:body+='<p>沒有標記位置。</p>'
        for c in r['candidates']:
            x,y,w,h=(c[k] for k in ('x','y','w','h'));side=max(96,w+48,h+48)
            x0=max(0,min(width-side,x+w//2-side//2));y0=max(0,min(height-side,y+h//2-side//2));cw=min(side,width-x0);ch=min(side,height-y0)
            body+=f'<article id="candidate-{c["id"]}"><h3>位置 {c["id"]}</h3>'
            if c.get('wire_review'):body+='<p>算法提示：疑似線材位移。</p>'
            body+='<div class="pair">'
            for label,file in [('參照圖：相同位置','reference.png'),('待測圖','aligned.png')]:
                body+=f'<div><b>{label}</b><svg viewBox="{x0} {y0} {cw} {ch}" xmlns="http://www.w3.org/2000/svg"><image href="{file}" width="{width}" height="{height}"/><rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="#e1263b" stroke-width=".7"/></svg></div>'
            body+='</div></article>'
        body+='<details><summary>AI 分數、對齊資訊與原始結果</summary><a href="technical.html">查看技術明細</a> · <a href="result.json">原始 JSON</a></details>'
        save(folder/'report.html',page(heading,body))
    (ROOT/'readable-report.json').write_text(json.dumps(dict(images=190,good_tests=139,good_false_alarm_images=84,good_false_alarm_boxes=128,ng_tests=47,ng_complete_object_audit=False,existing_visual_checks=2),indent=2))
    print('Rebuilt summary, OK/NG lists and all 190 image pages; analysis results unchanged')

if __name__=='__main__':main()
