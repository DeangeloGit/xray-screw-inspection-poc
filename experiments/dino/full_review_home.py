"""Full-dataset report front page. Comparisons are supplementary, never the entry point."""
import html
from pathlib import Path
esc=lambda x:html.escape(str(x))
def build_home(cases,rows,s,save,nav,types):
    body=nav+'<h1>目前版本：全圖資良品與不良品檢測結果</h1><p>DINO 47 張螺絲＋65 張非螺絲範例 · 同時判斷參照與待測圖 · 沿用原差分候選</p>'
    body+=f'<div class="answer"><p><b>良品：139 張，139 張零誤報。</b>原差分 128 框，AI 排除 128 框。</p><p><b>不良品：47 張，原差分 2665 框，AI 排除 {s["NG"]["paired"]["removed"]} 框，保留 {s["NG"]["paired"]["kept"]} 框。</b></p><p>下方收錄全部照片與候選，不只列出變動案例。保留框不等於螺絲顆數，排除框也不保證刪對。</p><p><a href="good.html">進入良品誤報 →</a>　<a href="bad.html">進入不良品檢測 →</a></p></div>'
    body+='<h2>依機種開始查看</h2><p>檢視順序：機種 → 線材／板件邊界／元件外觀／U 形結構／待確認 → 相近位置。先看代表圖，再展開同類全部照片。</p>'
    body+='<table><tr><th>機種</th><th>良品照片</th><th>良品剩餘誤報框</th><th>不良品照片</th><th>不良品保留／排除框</th><th>查看報告</th></tr>'
    for machine in ['MPT10','MPT12','KPH33','MPT11']:
        rs=[r for r in rows if r['machine']==machine and not r['is_reference']];zs=[z for z in cases if z['machine']==machine]
        good=[r for r in rs if r['label']=='OK'];bad=[r for r in rs if r['label']=='NG'];gz=[z for z in zs if z['label']=='OK'];bz=[z for z in zs if z['label']=='NG']
        ng=f'{sum(z["paired_keep"] for z in bz)}／{sum(not z["paired_keep"] for z in bz)}' if bad else '未提供'
        links=[]
        if good:links.append(f'<a href="good-{machine}.html">良品分類 →</a>')
        if bad:links.append(f'<a href="bad-{machine}.html">不良品分類 →</a>')
        body+=f'<tr><td>{machine}</td><td>{len(good) if good else "未提供"}</td><td>{sum(z["paired_keep"] for z in gz) if good else "—"}</td><td>{len(bad) if bad else "未提供"}</td><td>{ng}</td><td>'+ ' · '.join(links)+'</td></tr>'
    body+='</table><h2>報告包含哪些內容？</h2><ul><li>139 張良品＋47 張不良品，每張都有本次保留／排除結果；零候選照片也收錄。</li><li>全部 2793 個候選都有參照／待測對照圖、分類標示及同類案例連結。</li><li>另收錄 4 張正常參照圖，自比結果獨立列出，不混入成效。</li></ul><p><a href="references.html">查看 4 張參照圖 →</a></p>'
    body+='<details><summary>附加資料：螺絲核對與版本差異</summary><p><a href="checks.html">既有螺絲與誤報核對 →</a>　<a href="comparison.html">原版／新增範例／雙圖的差異比較 →</a></p><p>雙圖規則仍有疑似誤刪風險。新範例可能與本批圖資重複，結果屬開發測試，並非獨立準確率驗收。此版僅供本次測試，正式設定未切換。</p></details>'
    save('index.html','全圖資良品與不良品檢測結果',body)
    refs=[r for r in rows if r['is_reference']]
    body=nav+'<h1>正常參照圖：4 張</h1><p>參照圖自比結果不計入良品與不良品成效。以下保留完整照片入口。</p><table><tr><th>機種</th><th>照片</th><th>查看</th></tr>'
    for r in refs:body+=f'<tr><td>{esc(r["machine"])}</td><td>{esc(Path(r["relative"]).name)}</td><td><a href="photos/{r["sha256"]}.html">查看完整參照圖 →</a></td></tr>'
    save('references.html','正常參照圖',body+'</table>')
