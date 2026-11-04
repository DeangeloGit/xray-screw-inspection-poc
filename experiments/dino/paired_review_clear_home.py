"""Compose a clear report home from saved results only; no inference imports."""
import hashlib,html,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'workspace/added-object-pilot-20261103'
FIXED=ROOT/'workspace/dino-fixed-crop-recognition-20261103'

def read(path):return json.loads(path.read_text(encoding='utf-8'))
def word(pred):return '有螺絲' if pred['screw'] else '沒有螺絲'

def build_home(out,write,extra_cases,extra_rows,extra_table):
    inputs=[OLD/'plan.json',FIXED/'results.json',FIXED/'equal-vote-results.json',
            out/'plan.json',out/'results.json',out/'summary.json']
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    source=read(OLD/'plan.json')['cases'][:2]
    original=read(FIXED/'results.json')[:2]
    improved=read(FIXED/'equal-vote-results.json')[:2]
    assert [z['key'] for z in source]==['current-94','current-34']
    assert all(z['key']==a['key']==b['key'] for z,a,b in zip(source,original,improved))
    old_pairs=[a['protocols']['all_47_65']['original_cls'] for a in original]
    new_pairs=[b['protocols']['all_47_65'] for b in improved]
    assert [p['keep'] for p in old_pairs]==[False,False]
    assert [p['keep'] for p in new_pairs]==[True,True]
    assert [(z['name'],z['id']) for z in extra_cases[:2]]==[('MPT11/NG/5.png',2),('MPT11/NG/9.png',1)]
    assert all(r['keep']['original'] and r['keep']['equal'] for r in extra_rows[:2])
    false_alarms=[n for n,r in enumerate(extra_rows,1) if r['group']=='normal' and r['keep']['equal'] and not r['keep']['original']]
    assert false_alarms==[8]
    body='''<h1>分清楚兩組案例：原本沒判對的兩顆、額外驗證案例</h1>
    <div class="answer"><b>原本那兩顆有改善；額外案例沒有增加判對，並多出 1 個線材誤報。</b>
    <p>下面兩組是不同圖片。先前「原本 2 個判對」指的是另外找到的 5.png、9.png，並非你指出的斜螺絲與圓頭螺絲。</p></div>
    <p>本頁的「新方法」固定指：<b>整體與小區域各占一半</b>，保留完整 47＋65 張範例；沒有使用重新定位框，也沒有用待確認代替判斷。本次只重整已保存的報告。</p>
    <nav><a href="#original-problems">一、原本沒判對的兩顆螺絲</a><a href="#additional-cases">二、額外驗證案例</a><a href="#new-wire-alarm">新增線材誤報</a></nav>
    <h2>先看兩組各自的結果</h2>
    <table><tr><th>是哪一組？</th><th>原本 DINO</th><th>新方法</th></tr>
    <tr><td>原本問題：斜螺絲 #94、圓頭 #34</td><td>0／2 符合要求</td><td>2／2 符合要求</td></tr>
    <tr><td>額外驗證：5.png #2、9.png #1</td><td>2／2 符合要求</td><td>2／2 符合要求，沒有增加</td></tr>
    <tr><td>額外驗證：5 個應報新增螺絲的位置<br><small>依助手本輪參照／待測對照圖核對</small></td><td><b>5 個都判錯：全部漏報</b><br><small>4 個待測判沒有；1 個兩圖都判有</small></td><td><b>5 個都判錯：全部漏報</b><br><small>4 個待測判沒有；1 個兩圖都判有</small></td></tr>
    <tr><td>額外驗證：50 個正常位置</td><td>0 個誤報</td><td>1 個線材誤報</td></tr></table>
    <p>符合要求＝<b>參照圖判沒有螺絲、待測圖判有螺絲</b>。依這五處的對照圖，本輪預期都應報新增螺絲，所以沒有報出就是判錯，不算正確排除。這是助手的看圖核對，未冒充使用者人工標記，也未更動原人工紀錄。<a href="screws.html#case-3">看這五個位置的對照圖 →</a></p>
    <section id="original-problems"><h2>一、原本沒判對的兩顆螺絲</h2>
    <p>這就是你指出問題、展開研究的兩顆。同一張 MPT12 照片中的斜螺絲與圓頭螺絲，並非下面的 5.png、9.png。</p>'''
    for n,(z,a,b,title) in enumerate(zip(source,old_pairs,new_pairs,['斜螺絲','圓頭螺絲']),1):
        body+=f'<article id="original-{z["id"]}"><h3>原本問題 {n}：{title} · 位置 {z["id"]}</h3><p class="note">MPT12／{html.escape(z["name"])}</p>'
        body+=f'<div class="labels"><b>左：參照圖　／　右：待測圖</b></div><img class="pair" src="../{OLD.name}/images/{n}-pair.jpg">'
        body+='<table><tr><th>方法</th><th>參照圖判斷</th><th>待測圖判斷</th><th>符合要求？</th></tr>'
        for name,p in [('原本 DINO',a),('新方法：各占一半',b)]:
            body+=f'<tr><td>{name}</td><td>{word(p["reference"])}</td><td>{word(p["target"])}</td><td>{"是" if p["keep"] else "否"}</td></tr>'
        finding='原本把待測的斜螺絲判成沒有螺絲；新方法判對兩張。' if n==1 else '原本連參照圖也判成有螺絲，因此未報出新增螺絲；新方法把參照圖改判為沒有螺絲。'
        body+='</table><p><b>'+finding+'</b></p><details><summary>看 DINO 實際收到的兩張小圖</summary><p>新舊方法用完全相同的小圖，沒有改框。</p>'
        for side,label in [('reference','參照小圖'),('target','待測小圖')]:
            body+=f'<figure><figcaption>{label}</figcaption><img src="../{FIXED.name}/images/{n}-{side}.png"></figure>'
        body+=f'</details><p><a href="{(Path(z["source"])/"reference.png").as_uri()}">完整參照圖</a> · <a href="{(Path(z["source"])/"aligned.png").as_uri()}">完整待測圖</a> · <a href="#original-problems">返回原本問題案例</a></p></article>'
    body+='''<p>這兩顆是用來研究方法的原始問題案例；判對代表改善了這兩個問題，不能單憑它們推論其他圖片也會改善。</p></section>
    <section id="additional-cases"><h2>二、額外驗證案例</h2>
    <p><b>這是後來另外挑選的 57 個位置、41 張照片，不包含上面的原本兩顆。</b>以下先列兩個有既有螺絲標記的額外案例。它們原本就判對，新方法仍判對。</p>'''
    for n in [1,2]:
        z=extra_cases[n-1]
        body+=f'<article id="additional-screw-{n}"><h3>額外螺絲 {n}：{html.escape(z["name"])} · 位置 {z["id"]}</h3><p>另找的驗證案例；不是原本問題的斜螺絲 #94 或圓頭 #34。</p><img class="pair" src="images/{n}-pair.jpg">'+extra_table(n)
        body+=f'<p><b>原本判對，新方法也判對；本例沒有新增改善。</b></p><p><a href="screws.html#case-{n}">查看此額外案例的小圖與完整照片 →</a></p></article>'
    body+='''<h3>其餘額外案例也全部保留</h3><ul>
    <li><a href="screws.html#case-3">5 個應報新增螺絲的位置：看新舊判斷及對照圖</a>，依助手本輪看圖預期，新舊方法都是五處全錯、全部漏報。</li>
    <li><a href="normal.html">50 個正常位置：看全部線材、板件與其他結構</a>，誤報從 0 增加到 1。</li>
    </ul><p><a href="additional.html">額外驗證案例完整總覽 →</a> · <a href="sources.html">額外案例的選擇與來源核對 →</a></p></section>'''
    n=8;z=extra_cases[n-1]
    body+=f'<section id="new-wire-alarm"><h2>額外驗證中的新增線材誤報</h2><h3>{html.escape(z["name"])} · 位置 {z["id"]}</h3><p><b>實際看到的是線束位置改變，沒有新增螺絲。新方法卻把待測圖判成有螺絲。</b></p><img class="pair" src="images/{n}-pair.jpg">'+extra_table(n)
    p=extra_rows[n-1]['pair']
    assert not p['target']['whole']['screw'] and p['target']['local']['screw'] and p['target']['equal']['screw']
    body+='<div class="answer warn"><b>這個誤報怎麼來的？</b><ol><li>原本 DINO 判兩張都沒有螺絲，這例原本是對的。</li><li>新法的「整體外觀」仍把待測圖判為非螺絲；「小區域特徵」卻偏向螺絲。</li><li>兩部分各占一半後，小區域的影響蓋過整體，待測圖變成有螺絲；參照圖則仍判沒有，於是誤報新增螺絲。</li></ol><p>兩類比較的差距很小，不代表模型明確認出了螺絲。另加入不同朝向範例後，整體比較對正常的優勢也縮小，所以不能將原因只歸給小區域。</p><p><b>目前的原因推測：</b>小區域描述取平均後，未能可靠區分「連續線束」和「有頭、有桿的螺絲」。粗黑輪廓或背景可能干擾，但沒有證據能指定某一條線或某一個像素就是原因。這例證明目前的等權組合會引入誤報，並非取圖沒包含物件。</p></div>'
    for side,label in [('reference','DINO 收到的參照小圖'),('target','DINO 收到的待測小圖')]:body+=f'<figure><figcaption>{label}</figcaption><img src="images/{n}-{side}.png"></figure>'
    body+=f'<p><a href="normal.html#case-{n}">查看線材誤報完整資料與同類案例 →</a></p></section>'
    body+='''<div class="answer warn"><b>現在的結論：</b>新方法改善了原本那兩顆，但額外驗證沒有增加判對，反而多出一個線材誤報，所以尚未套用正式流程。</div>
    <p class="note">額外案例已排除可辨識的重複，但螺絲範例缺完整原始來源，不能保證完全獨立。原本問題與額外驗證分開統計，不把兩組混成單一準確率。</p>
    <p>本次只整理報告，沒有重跑檢測／DINO，沒有變更正式流程、範例、設定或人工紀錄。<a href="report-reorganization.json">已保存結果與檔案核對</a> · <a href="validation.json">圖片與連結核對</a></p>'''
    write('index.html','原本問題與額外驗證：兩組分開看',body)
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items())
    (out/'report-reorganization.json').write_text(json.dumps(dict(original_problem_cases=2,additional_cases=57,
        original_old_success=0,original_new_success=2,additional_marked_old_success=2,additional_marked_new_success=2,
        additional_normal_old_false_alarms=0,additional_normal_new_false_alarms=1,
        saved_result_hashes=hashes,saved_results_unchanged=True,inference_runs=0,detection_runs=0,production_changes=False),ensure_ascii=False,indent=2),encoding='utf-8')
