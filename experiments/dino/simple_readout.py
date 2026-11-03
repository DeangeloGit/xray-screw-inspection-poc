"""Short visual reading path; preserve the detailed audit and all experiment data."""
from pathlib import Path
from html import escape
import json,shutil
from experiments.dino.two_directions import OUT,read

STYLE='''*{box-sizing:border-box}body{margin:0;background:#f5f8f9;color:#183c45;font:18px/1.7 "Microsoft JhengHei",sans-serif}main{max-width:1040px;margin:32px auto;padding:0 24px}nav{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:30px}a{color:#007b85;text-underline-offset:4px}nav a{padding:8px 15px;border:1px solid #b9ced2;border-radius:6px;text-decoration:none}nav a.active{background:#007b85;color:white}h1{font-size:30px;line-height:1.4;margin:0 0 14px}h2{font-size:23px;line-height:1.5;margin:0 0 14px}h3{font-size:20px;margin:0 0 8px}p{margin:10px 0}.lead{font-size:23px;font-weight:bold}.intro{border-left:5px solid #007b85;padding:14px 22px;background:white;margin:22px 0 30px}.card{background:white;border:1px solid #d9e3e5;border-radius:8px;padding:24px;margin:22px 0}.muted{color:#5c747a;font-size:15px}.label{display:grid;grid-template-columns:1fr 1fr;font-size:17px;font-weight:bold;text-align:center;background:#eaf1f3;padding:8px}.pairimg{width:100%;display:block;max-width:800px;margin:auto}.caption{text-align:center;font-size:15px;color:#5c747a}.result{padding:12px 16px;background:#edf5f5;margin-top:14px}.risk{background:#fff2eb}.twocards{display:grid;grid-template-columns:1fr 1fr;gap:20px}.twocards .card{margin:0}details{padding:16px 20px;margin:20px 0;background:white;border:1px solid #d9e3e5;border-radius:6px}summary{cursor:pointer;font-weight:bold}table{border-collapse:collapse;width:100%;margin-top:14px}td,th{border:1px solid #d9e3e5;padding:10px;text-align:left}.next{border-top:1px solid #cadbde;padding-top:20px;margin-top:28px}figure{margin:15px 0}.ai{display:flex;align-items:center;gap:24px}.ai img{width:200px;max-width:40%}@media(max-width:700px){.twocards{grid-template-columns:1fr}main{padding:0 14px}h1{font-size:25px}.card{padding:16px}.ai{gap:12px}}'''
def main(archive=True):
    if archive:
        for name in ['index','a','b']:
            src=OUT/f'{name}.html';dest=OUT/f'{name}-details.html'
            if src.exists():
                s=src.read_text(encoding='utf-8')
                # Do not replace original detail archives with these short pages.
                if '<!--simple-readout-->' not in s:
                    s=s.replace('href="a.html"','href="a-details.html"').replace('href="b.html"','href="b-details.html"')
                    dest.write_text(s,encoding='utf-8')
    def save(name,title,body):
        nav='<nav aria-label="報告導覽">'+''.join(f'<a class="{"active" if name==n else ""}" href="{n}.html">{t}</a>' for n,t in [('index','報告首頁'),('a','圖一：誤報有沒有變少？'),('b','圖二：為什麼漏掉螺絲？')])+'</nav>'
        (OUT/f'{name}.html').write_text(f'<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>{STYLE}</style></head><body><!--simple-readout--><main>{nav}{body}<p class="muted next">本次只做離線分析。正式程式、模型與設定未修改。</p></main></body></html>',encoding='utf-8')
    a=[z for z in read(OUT/'a-cases.json') if z['would_discard']];b=read(OUT/'b-cases.json')
    def pair(z):
        return f'<div class="label"><span>原本的參照圖</span><span>這次的待測圖</span></div><img class="pairimg" src="images/{z["key"]}-pair.jpg" alt="左側參照圖，右側待測圖，紅框為原差分位置"><p class="caption">紅框只是這次檢查的位置。</p>'
    def source(z,kind):
        return f'<p class="muted">{escape(Path(z["name"]).name)} · 位置 {z["id"]}　<a href="{kind}-details.html#case-{z["key"]}">查看此例完整紀錄</a></p>'
    save('index','兩個問題：先看結論','''<h1>這次只回答兩個問題</h1><p>選一個問題看即可。每頁先看例圖，完整數字放在下方展開。</p><div class="twocards"><section class="card"><h2>圖一：原本就有螺絲，卻又被框出來</h2><p class="lead">有改善，但還不能直接用。</p><p>多看參照圖能排除一些誤報；可是「兩邊都有螺絲就刪掉」，也會刪到真正新增的物件。</p><p><a href="a.html">看一個成功例子、一個失敗例子 →</a></p></section><section class="card"><h2>圖二：明明多了螺絲，DINO 卻刪掉</h2><p class="lead">已找到案例，還沒有解決。</p><p>有些螺絲完整出現在 AI 小圖裡，仍被判錯；另一些則與線材重疊，或沒有截完整。</p><p><a href="b.html">看錯在哪裡、接下來怎麼測 →</a></p></section></div>''')
    good=a[7];bad=a[3]
    body='<h1>圖一：多看參照圖，有沒有用？</h1><div class="intro"><p class="lead">有用，但目前的刪除規則太粗，還不能套用。</p><p>這次測的是：待測圖與參照圖都被 DINO 判成螺絲，就把這個框刪掉。</p></div>'
    body+='<section class="card"><h2>① 這個例子：刪對了</h2><p>兩張圖原本都有這顆圓形物件，只是明暗和旁邊線材變了。</p>'+pair(good)+'<p class="result"><b>原本：</b>留下誤報框。<br><b>多看參照圖後：</b>會刪掉這個框，符合預期。</p>'+source(good,'a')+'</section>'
    body+='<section class="card"><h2>② 這個例子：卻會刪錯</h2><p>右圖在原有黑色圓形物件旁邊，多了一個灰色圓形物件。</p>'+pair(bad)+'<p class="result risk"><b>問題：</b>參照小圖裡的黑色圓形物件也被 DINO 當成螺絲。兩邊都被叫作螺絲，程式就準備刪框，卻沒發現右圖多了一個物件。</p>'+source(bad,'a')+'</section>'
    body+='<div class="intro"><h2>所以接下來要改什麼？</h2><p>不能只問「兩邊有沒有螺絲」。要確認：<b>是不是同一個物件，而且旁邊沒有多出另一個。</b></p><p>這一步尚未實作，先不改正式流程。</p></div><details><summary>想看整批驗證數字，再展開這裡</summary><p>檢查全部 330 個原本保留的框，這個簡單規則會刪掉 74 個。我逐一看圖核對：</p><table><tr><th>這 74 個框的情況</th><th>框數</th></tr><tr><td>看起來是原有物件或線材變化，可以減少誤報</td><td>58</td></tr><tr><td>可見新增疑似螺絲，有誤刪風險</td><td>9</td></tr><tr><td>目前無法可靠判定</td><td>7</td></tr></table><p class="muted">這是助手的目視核對，不是使用者確認的完整標準答案。框數不等於螺絲顆數。</p><p><a href="a-details.html">查看完整 74 框分類與對照圖 →</a></p></details>'
    save('a','圖一：有改善，但會誤刪',body)
    z=b[1]
    body='<h1>圖二：明明有螺絲，為什麼被刪？</h1><div class="intro"><p class="lead">已找到問題案例；目前是在查原因，還沒有解決。</p><p>先看一個已標記的真螺絲。這個例子說明：不能把所有誤刪都怪在裁圖。</p></div><section class="card"><h2>這顆螺絲，原本沒有，這次多出來了</h2>'+pair(z)+'<div class="ai"><img src="images/'+z['key']+'-input-1.png" alt="DINO 實際看到的小圖，螺絲的頭和桿仍可見"><div><h3>這就是 DINO 實際看到的圖片</h3><p>頭和桿都還看得到。<br><b>但 DINO 仍判成非螺絲，將它排除。</b></p></div></div>'+source(z,'b')+'</section>'
    body+='<div class="intro"><h2>這一類，接下來應該測什麼？</h2><p>先改善拿來比對的螺絲範例，補進<b>與現場 X 光更相近的外觀</b>，再用沒有拿去當範例的圖片測試。</p><p>這是下一步要驗證的方法，目前還不能說換範例一定有效。</p></div><details><summary>另有兩種情況，不能一起處理</summary><h3>螺絲與線材、原有元件重疊</h3><p>小圖裡有好幾種東西，可能影響判斷。要另成一組測試。</p><h3>螺絲沒有完整留在 AI 小圖裡</h3><p>這一類才另外測完整取圖，並確認不會因此多出線材誤報。</p><p><a href="b-details.html">查看分類例圖與實際 AI 小圖 →</a></p></details><details><summary>這次到底看了多少？</summary><p>看過 40 個代表候選，整理出 16 個追查位置：2 個已有目視標記，14 個仍屬疑似誤刪。</p><p>這不是整批漏檢總數，也不是已救回 16 顆螺絲。</p><p><a href="b-details.html">查看全部案例與原因分析 →</a></p></details>'
    save('b','圖二：先看一個完整可見卻被刪的螺絲',body)
    print('Simplified index, A, B; preserved detailed reports and all data.')
if __name__=='__main__':main()
