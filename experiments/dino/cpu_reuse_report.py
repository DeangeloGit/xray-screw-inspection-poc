"""Plain-language small-experiment report, using saved measurements only."""
import json
import html
import os
import statistics
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote, unquote, urlparse
from html.parser import HTMLParser

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'workspace/dino-cpu-reuse-20261104'
TYPES={'wire':'線材','edge':'板件邊界','component':'元件外觀','structure':'U 形結構','unknown':'待確認'}


def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def link(path):return quote(Path(os.path.relpath(path,OUT)).as_posix())
def esc(value):return html.escape(str(value))
def sec(value):return f'{value:.2f}'
def judgement(value):return '有螺絲' if value else '沒有螺絲'
CSS="""body{font:18px/1.7 'Microsoft JhengHei',sans-serif;color:#173e4c;background:#f5f8f9;max-width:1180px;margin:30px auto;padding:0 22px}h1{font-size:32px}h2{font-size:25px;margin-top:35px}a{color:#007c88}nav{display:flex;gap:25px}.answer{background:white;border-left:6px solid #00838c;padding:22px;margin:22px 0}table{border-collapse:collapse;width:100%;background:white}td,th{border:1px solid #d7e1e5;padding:12px;text-align:left}th{background:#e8f1f4}details,article{background:white;border:1px solid #d8e2e6;border-radius:8px;margin:20px 0;padding:18px}img{max-width:100%;height:auto}.inputs{display:flex;gap:20px}.inputs figure{margin:10px 0;flex:1}.inputs img{max-width:224px}.muted{color:#526b76}.good{color:#007b64}summary{cursor:pointer}small{font-size:15px}"""


def write(name,title,body):
    (OUT/name).write_text(f'<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><style>{CSS}</style><nav><a href="index.html">省了幾秒、結果有沒有變</a><a href="cases.html">原有59案例對照</a></nav>{body}</html>',encoding='utf-8')


def main():
    runs=load(OUT/'runs.json');data=[dict(load(r['path']),measurement=r['path']) for r in runs]
    baseline=[d for d in data if d['cpu_reuse']=='off'];warm=[d for d in data if d['cpu_reuse']=='warm'];cold=[d for d in data if d['cpu_reuse']=='cold'][0]
    assert len(baseline)==len(warm)==2
    mean=lambda rows,key:statistics.mean(d[key] for d in rows)
    old_total,new_total=mean(baseline,'total_seconds'),mean(warm,'total_seconds')
    old_analysis,new_analysis=mean(baseline,'analysis_seconds'),mean(warm,'analysis_seconds')
    saving=old_total-new_total;analysis_saving=old_analysis-new_analysis
    def affected(d):
        s=d['detector_stage_seconds']
        other=s['detector_total']-sum(s[k] for k in ('read','register','refine','proposals','legacy_proposals','write_image','ai_total'))
        return sum(s[k] for k in ('read','register','proposals','legacy_proposals'))+other
    affected_before=statistics.mean(affected(d) for d in baseline)
    affected_after=statistics.mean(affected(d) for d in warm)
    upstream=load(OUT/'upstream-verification.json');ai=load(OUT/'cases/cpu-summary.json')
    prior=load(ROOT/'workspace/dino-four-remaining-20261103/restricted-results.json')
    predictions=load(OUT/'cases/cpu-results.json');cases=load(ROOT/'workspace/dino-learn-joint-20261103/results.json')
    assert upstream['cases']==len(cases)==len(predictions)==59
    assert not ai['decision_changes'] and not ai['input_differences'] and not upstream['candidate_changes']
    assert ai['normal_false_alarms']==0 and all(ai['protected_screws'].values())
    proof=[r['verification'] for r in runs]
    assert all(not p['candidate_changes'] and not p['decision_changes'] and not p['dino_input_changes'] and not p['image_changes'] for p in proof)
    def delta(n):return f'省 {n:.2f} 秒' if n>=0 else f'多 {-n:.2f} 秒'
    timing_rows=''
    for i,part in enumerate(baseline[0]['sections']):
        a=statistics.mean(d['sections'][i]['seconds'] for d in baseline)
        b=statistics.mean(d['sections'][i]['seconds'] for d in warm)
        timing_rows+=f'<tr><td>{esc(part["name"])}</td><td>{a:.2f}</td><td>{b:.2f}</td><td>{delta(a-b)}</td></tr>'
    initial=load(OUT/'gpu-initial.json');g0,g1=[load(r['path']) for r in initial]
    conclusion=('本次平均'+delta(saving)+'；尚需更多穩定測量確認' if saving>0 else '這輪沒有讓CPU整體測速更快')
    body=f'''<h1>{conclusion}</h1>
<p><strong>下列約85秒是CPU測速。</strong>因GPU在重測途中再次限速，原／新方法都改用CPU公平比較；前次約35秒是GPU測速，設備不同，不能直接比較。</p>
<div class="answer"><strong>同一張圖、同樣檢測方法：CPU 取圖到結果 {old_total:.2f} → {new_total:.2f} 秒。</strong>
<p>原方法與新方法各測兩次，順序為原 → 新 → 新 → 原。實際分析 {old_analysis:.2f} → {new_analysis:.2f} 秒，{delta(analysis_saving)}。15 秒穩定等待與掃描方式均未修改。</p>
<p>涉及本次改動的階段（讀圖、對齊、差分與其他整理，含共用作業）：{affected_before:.2f} → {affected_after:.2f} 秒，{delta(affected_before-affected_after)}。這與包含DINO及等待的總時間分開看。</p>
<p><strong>137 個候選框的位置、DINO 看到的圖片、參照／待測判斷全部不變；仍保留 19 框。</strong>19 是候選框數，不是螺絲顆數。</p>
<p>原本兩顆及救回的長螺絲維持判對；50 個正常位置仍無新增誤報。原本未判出的 3 個疑似螺絲位置仍未判出，沒有靠加速改判。</p></div>
<p>這是依本次要求進行的單張測速與原有59案例驗證，沒有重跑全圖資，沒有更動正式流程、模型、設定或人工紀錄。速度改善不等於辨識率改善。</p>
<h2>這次實際省掉哪些工作？</h2><table><tr><th>項目</th><th>原方法</th><th>新方法</th></tr>
<tr><td>正常參照圖</td><td>每張待測圖重做影像準備、輪廓與對齊特徵</td><td>相同參照圖重用；內容變更時重新計算</td></tr>
<tr><td>舊版核對框所用的大型空白位移圖</td><td>這張圖建立39次</td><td>建立1次，共用39次</td></tr>
<tr><td>兩次候選搜尋共用的背景與差異資料</td><td>各算一次，共2次</td><td>算1次後共用</td></tr></table>
<p>沒有縮小圖片、減少候選、修改對齊方向搜尋、少存圖片、調整DINO門檻或改動47＋65範例。參照圖仍核對內容，避免使用過期資料。</p>
<h2>第一次使用參照圖也有成本</h2>
<p>上面的新方法時間是參照圖已備妥後的後續照片。預先準備參照圖平均另花 <strong>{mean(warm,'reference_preparation_seconds'):.2f} 秒</strong>，不能當成免費。</p>
<p>另外測了一次「沒有預先準備」：準備參照圖包含在分析內，取圖到結果 <strong>{cold['total_seconds']:.2f} 秒</strong>，其中分析 {cold['analysis_seconds']:.2f} 秒。這是單次數值，不與兩次平均假裝成完全相同負載。</p>
<h2>每一段花多久？</h2><p>單位：秒；原方法與新方法各兩次平均。其他未修改階段也會因負載波動而變快或變慢，不能把全部差異都歸功於這兩項修改。</p>
<table><tr><th>階段</th><th>原方法</th><th>新方法（參照已備妥）</th><th>本次差異</th></tr>{timing_rows}<tr><th>總計</th><th>{old_total:.2f}</th><th>{new_total:.2f}</th><th>{delta(saving)}</th></tr></table>
<p class="muted">「等待」欄只計程式暫停的時間；掃描期間也有經過時間，因此該欄可能不到15秒，但檔案穩定門檻仍是15秒。</p>
<h2>為什麼這次主要使用CPU計時？</h2>
<p>先用GPU測得 {g0['total_seconds']:.2f} → {g1['total_seconds']:.2f} 秒，少 {g0['total_seconds']-g1['total_seconds']:.2f} 秒；但後續重測中顯示卡再次降到300 MHz／10 W。受限那次已停止，沒有混進平均，也沒有把未完成測試算成結果。</p>
<p>因此主要結論改用CPU交錯重測。前面的GPU數字只是一組初步結果，不能把CPU省下的秒數直接套到GPU。<a href="gpu-throttle-recurred.txt">查看這次再次限速的紀錄</a>。</p>
<h2>原有案例有沒有變？</h2><table><tr><th>案例</th><th>結果</th></tr><tr><td>原本兩顆問題螺絲</td><td>都維持「參照沒有、待測有」</td></tr><tr><td>救回的長螺絲及另3個已成功位置</td><td>全部維持原判斷</td></tr><tr><td>原本未判出的3個疑似螺絲位置</td><td>仍未判出，未改善也未惡化</td></tr><tr><td>42個線材、2個板件邊界、4個元件、2個U形結構</td><td>50個正常位置全部維持無新增螺絲誤報</td></tr></table>
<p>沿用原有開發標記；疑似螺絲沒有升格為人工確認。<a href="cases.html">查看全部59案例的原／新判斷與對照圖 →</a></p>
<details><summary>每次原始時間與一致性證據</summary><ul>'''
    for i,d in enumerate(data,1):
        label={'off':'原方法','warm':'新方法：參照已備妥','cold':'新方法：第一次準備也計時'}[d['cpu_reuse']]
        body+=f'<li>{i}. {label}：總共 {d["total_seconds"]:.2f} 秒，分析 {d["analysis_seconds"]:.2f} 秒。<a href="{link(Path(d["measurement"]))}">完整分段紀錄</a></li>'
    body+=f'''</ul><p>每次均核對137個候選、全部{proof[0]['images']}張輸出PNG、對齊矩陣、結構變化、舊版核對候選與DINO輸入圖片。既有59案例分布在{upstream['sources']}組參照／待測圖，逐組比較參照準備、對齊特徵與候選產生結果一致；使用既有對齊圖核對，沒有重跑整批原始圖資。</p><p>
<a href="runs.json">單張框與圖片核對</a> · <a href="upstream-verification.json">42組影像核對</a> · <a href="cases/cpu-summary.json">59案例DINO核對</a> · <a href="preservation-after.json">正式檔案保持不變</a></p></details>'''
    write('index.html','CPU加速小實驗：省了幾秒、結果有沒有變',body)
    def card(z):
        n=z['number'];old=prior[n-1]['new'];new=predictions[n-1]['new']
        machine=z.get('machine','MPT12');category=z.get('category','unknown')
        annotation='沿用目視疑似，尚未升格人工確認' if z['group']=='five_visual_screws' else '沿用前次開發案例標記'
        rows=''
        for name,p in [('原方法',old),('減少CPU重複計算',new)]:
            rows+=f'<tr><td>{name}</td><td>{judgement(p["reference"]["screw"])}</td><td>{judgement(p["target"]["screw"])}</td><td>{"是" if p["keep"] else "否"}</td></tr>'
        content=f'<article id="case-{n}"><h3>{esc(z["name"])} · 位置 {z["id"]}</h3><p><strong>結果不變。</strong>{annotation}；類型：{TYPES[category]}。</p><img loading="lazy" src="{link(Path(z["context"]))}" alt="既有參照與待測位置對照"><table><tr><th>方法</th><th>參照圖判斷</th><th>待測圖判斷</th><th>報新增螺絲？</th></tr>{rows}</table>'
        content+='<details><summary>DINO實際看到的圖片（本輪核對完全相同）</summary><div class="inputs">'
        for side,title in [('reference','參照圖'),('target','待測圖')]:
            image=ROOT/f'workspace/dino-four-remaining-20261103/images/{n}-final-{side}.png'
            content+=f'<figure><figcaption>{title}</figcaption><img loading="lazy" src="{link(image)}" alt="{title}DINO輸入"></figure>'
        content+='</div></details>'
        content+=f'<p><a href="{link(Path(z["source"])/"reference.png")}">完整參照圖</a> · <a href="{link(Path(z["source"])/"aligned.png")}">完整待測圖</a> · <a href="#machine-{machine}">返回此機種</a> · <a href="#type-{machine}-{category}">查看同類案例</a></p></article>'
        return content
    body='<h1>原有59案例：原方法與新方法的判斷全部相同</h1><p>依機種 → 類型 → 相近位置整理。類型沿用前次開發分類，並非本輪新增人工確認標籤。「待確認」只指外觀類型分組，DINO有／沒有螺絲的判斷均另外寫明。此處只收錄這次指定的小實驗案例。</p>'
    for machine in ['MPT10','MPT12','KPH33','MPT11']:
        selected=[z for z in cases if z.get('machine','MPT12')==machine]
        body+=f'<section id="machine-{machine}"><h2>{machine} · {len(selected)} 個案例</h2>'
        for category,title in TYPES.items():
            entries=[z for z in selected if z.get('category','unknown')==category]
            body+=f'<section id="type-{machine}-{category}"><h3>{title} · {len(entries)}</h3>'
            groups=defaultdict(list)
            for z in entries:
                c=z['c'];groups[(int((c['x']+c['w']/2)//100),int((c['y']+c['h']/2)//100))].append(z)
            for group in groups.values():
                body+=f'<p>相近位置 · {len(group)} 個案例（依對齊圖座標自動分組）</p>'+card(group[0])
                if len(group)>1:
                    body+=f'<details><summary>展開其餘 {len(group)-1} 個同類案例</summary>'+''.join(card(z) for z in group[1:])+'</details>'
            body+='</section>'
        body+='</section>'
    write('cases.html','原有59案例對照',body)
    class Check(HTMLParser):
        def __init__(self):super().__init__();self.refs=[];self.ids=set()
        def handle_starttag(self,tag,attrs):
            for k,v in attrs:
                if k in ('src','href'):self.refs.append(v)
                if k=='id':assert v not in self.ids,v;self.ids.add(v)
    documents={}
    for name in ('index.html','cases.html'):
        parser=Check();parser.feed((OUT/name).read_text(encoding='utf-8'));documents[(OUT/name).resolve()]=parser
    total_links=0
    for path,parser in documents.items():
        for url in parser.refs:
            parsed=urlparse(url)
            if parsed.scheme:continue
            target=(path.parent/unquote(parsed.path)).resolve() if parsed.path else path
            assert target.is_file(),target
            if parsed.fragment:assert parsed.fragment in documents[target].ids,(url,path)
            total_links+=1
    assert len([i for i in documents[(OUT/'cases.html').resolve()].ids if i.startswith('case-')])==59
    summary=dict(cpu_total_before=old_total,cpu_total_after=new_total,saved_seconds=saving,
        analysis_before=old_analysis,analysis_after=new_analysis,analysis_saved_seconds=analysis_saving,
        affected_before=affected_before,affected_after=affected_after,affected_saved_seconds=affected_before-affected_after,
        first_photo_total=cold['total_seconds'],reference_preparation_seconds=mean(warm,'reference_preparation_seconds'),
        candidate_changes=0,decision_changes=0,case_count=59,normal_false_alarms=0,unchanged_unresolved_cases=[5,7,9],
        links_checked=total_links,formal_changes=False,gpu_throttle_recurred=True)
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
