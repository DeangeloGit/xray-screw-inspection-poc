"""Plain-language report for the explicitly requested one-photo speed experiment."""
import json,statistics,os,html
from pathlib import Path
from urllib.parse import quote,unquote,urlparse
from html.parser import HTMLParser
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'workspace/dino-three-speed-20261104'
def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def link(p):return quote(Path(os.path.relpath(p,OUT)).as_posix())
def esc(s):return html.escape(str(s))
def main():
    runs=load(OUT/'timings.json'); assert len(runs)==15 and not any(r['changed_fields'] for r in runs)
    modes=['base','align','brightness','candidates','combined']
    names=dict(base='原方法（本次重新測量）',align='只改①：不同方向同時處理',brightness='只改②：明暗計算重用暫存',candidates='只改③：不同候選同時檢查',combined='①＋②＋③全部合併')
    avg={m:{k:statistics.mean(r['stages'][k] for r in runs if r['mode']==m) for k in runs[0]['stages']} for m in modes}
    baseline=avg['base'];new=avg['combined'];saved=baseline['total']-new['total']
    source=load(OUT/'case-source-verification.json'); assert source['sources']==source['expected_sources']
    ai=load(OUT/'dino-cases/cpu-summary.json'); cases=load(OUT/'dino-cases/cpu-results.json')
    original=load(ROOT/'workspace/dino-learn-joint-20261103/results.json')
    fullruns=load(OUT/'full-pipeline-runs.json');full={r['mode']:load(r['path']) for r in fullruns}
    proof=load(OUT/'full-pipeline-verification.json');preserved=load(OUT/'preservation-after.json')
    assert not preserved['changes'] and not ai['decision_changes'] and not ai['input_differences']
    rows=''
    for m in modes:
        a=avg[m];delta=baseline['total']-a['total'];vals=[r['stages']['total'] for r in runs if r['mode']==m]
        change='基準' if m=='base' else (f'省 {delta:.2f} 秒' if delta>=0 else f'慢 {-delta:.2f} 秒')
        rows+=f'<tr><td>{names[m]}</td><td>{a["register"]:.2f}</td><td>{a["proposals"]:.2f}</td><td>{a["refine"]+a["legacy_proposals"]:.2f}</td><td><b>{a["total"]:.2f}</b><br><small>{min(vals):.2f}～{max(vals):.2f}</small></td><td>{change}</td><td>相同</td></tr>'
    perrun=''.join(f'<tr><td>{r["run"]}</td><td>{names[r["mode"]]}</td><td>{r["stages"]["register"]:.3f}</td><td>{r["stages"]["proposals"]:.3f}</td><td>{r["stages"]["total"]:.3f}</td><td>完全相同</td></tr>' for r in runs)
    totals=sum(z['candidates'] for z in source['results'])
    def seconds(v):return f'{v:.2f} 秒'
    fullrows=''
    fields=[('從取圖到結果可讀取','total_seconds'),('其中：等待、取圖與匯入','folder_to_analysis_seconds'),('其中：開始分析到存好結果','analysis_seconds')]
    for title,key in fields:
        a,b=full['base'][key],full['combined'][key]
        delta=a-b;fullrows+=f'<tr><td>{title}</td><td>{seconds(a)}</td><td>{seconds(b)}</td><td>{"省" if delta>=0 else "慢"} {abs(delta):.2f} 秒</td></tr>'
    full_delta=full['combined']['total_seconds']-full['base']['total_seconds']
    folder_delta=full['combined']['folder_to_analysis_seconds']-full['base']['folder_to_analysis_seconds']
    ai_delta=full['combined']['detector_stage_seconds']['ai_total']-full['base']['detector_stage_seconds']['ai_total']
    full_timing_note=f'整趟實測 {full["base"]["total_seconds"]:.2f} → {full["combined"]["total_seconds"]:.2f} 秒，本次反而慢 {full_delta:.2f} 秒。取圖前段多花 {folder_delta:.2f} 秒（多等一次約3秒的掃描），AI整段也多花 {ai_delta:.2f} 秒；這些超過了本次完整流程內省下的處理時間。因此，目前只能說內部階段有縮短，尚未證明整張圖更快出答案。'
    casedict={r['number']:r for r in cases}
    def pairtext(pair):
        return f'參照圖：{"有螺絲" if pair["reference"]["screw"] else "沒螺絲"}；待測圖：{"有螺絲" if pair["target"]["screw"] else "沒螺絲"} → <b>{"判為新增螺絲" if pair["keep"] else "未判為新增螺絲"}</b>'
    def panel(z):
        n=z['number'];r=casedict[n];path=ROOT/'workspace/dino-four-remaining-20261103/images'
        context=f'<p><a href="{link(Path(z["context"]))}">查看先前的原位置對照圖</a></p>' if z.get('context') else ''
        note='原本與本次相同；正常案例未增加誤報。' if z['group']=='normal' else ('原本與本次都判出。' if r['new']['keep'] else '原本與本次都未判出；這輪加速沒有改善此案例。疑似螺絲仍待人工確認。')
        return f'''<details id="case-{n}"><summary>案例 {n}｜{esc(z['name'])}｜位置 {z['id']}｜{note}</summary>
<p>原方法：{pairtext(r['baseline'])}</p><p>本次複驗：{pairtext(r['new'])}</p>
<div class="images"><figure><figcaption>參照圖：DINO 實際輸入</figcaption><img loading="lazy" src="{link(path/f'{n}-final-reference.png')}" alt="案例{n}參照圖"></figure><figure><figcaption>待測圖：DINO 實際輸入</figcaption><img loading="lazy" src="{link(path/f'{n}-final-target.png')}" alt="案例{n}待測圖"></figure></div>{context}<p><a href="#cases">返回案例總覽</a></p></details>'''
    casehtml='<h3>原本沒判對、後來改善的兩顆螺絲</h3>'+''.join(panel(z) for z in original[:2])
    casehtml+='<h3>額外螺絲／疑似螺絲：7 處全部列出</h3>'+''.join(panel(z) for z in original[2:9])
    cats={'wire':'線材','edge':'板件邊界','component':'元件外觀','structure':'U 形結構','unknown':'待確認'}
    normals=[z for z in original if z['group']=='normal']
    for machine in sorted(set(z.get('machine','未標機種') for z in normals)):
        casehtml+=f'<h3>{esc(machine)}：正常案例</h3>'
        for cat,title in cats.items():
            group=[z for z in normals if z.get('machine','未標機種')==machine and z.get('category','unknown')==cat]
            casehtml+=f'<details><summary>{title}：{len(group)} 處（沿用既有分類，非新增人工標記）</summary>'+''.join(panel(z) for z in group)+'</details>'
    delta=lambda m,k:baseline[k]-avg[m][k]
    decisions='；'.join(f'{names[m].split("：")[-1]}：整段{"省" if baseline["total"]>=avg[m]["total"] else "慢"} {abs(baseline["total"]-avg[m]["total"]):.2f} 秒' for m in modes[1:])
    text=f'''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>三項加速小實驗：省幾秒、結果有沒有變</title>
<style>body{{font:18px/1.7 'Microsoft JhengHei',sans-serif;color:#173e4c;background:#f5f8f9;max-width:1250px;margin:30px auto;padding:0 22px}}h1{{font-size:32px}}h2{{font-size:25px;margin-top:34px}}table{{width:100%;border-collapse:collapse;background:white}}td,th{{padding:12px;border:1px solid #d7e2e6;text-align:left;vertical-align:top}}th{{background:#e8f1f4}}.answer{{background:white;border-left:6px solid #00838c;padding:20px 25px}}a{{color:#007e8a}}details{{border:1px solid #d7e2e6;background:white;padding:16px;margin:14px 0}}summary{{cursor:pointer}}.images{{display:flex;gap:24px;max-width:750px}}figure{{flex:1;margin:0}}img{{width:100%;object-fit:contain}}small{{color:#526b76;font-size:15px}}nav a{{margin-right:20px}}.scroll{{overflow-x:auto}}</style>
<nav><a href="#timing">時間結果</a><a href="#proof">結果核對</a><a href="#cases">全部59案例</a></nav>
<h1>內部階段省 {saved:.2f} 秒；整張出結果，本次未加快</h1>
<div class="answer"><p><b>對齊＋差分＋局部修正與核對：{baseline['total']:.2f} → {new['total']:.2f} 秒。</b>這是同一張圖、每版三次交錯測量的平均；{"縮短" if saved>=0 else "增加"} {abs(saved/baseline['total']*100):.1f}%。</p>
<p><b>137 個候選框、參照／待測的 DINO 判斷都相同。</b>既有59案例的判斷也相同：原本兩顆及後來已判出的螺絲維持；50個正常案例仍沒有誤報。</p>
<p><b>取圖到答案：{full['base']['total_seconds']:.2f} → {full['combined']['total_seconds']:.2f} 秒，本次較慢，尚未證明全流程加速。</b>原因與各段時間列在下方。</p>
<p>另有3個既有疑似螺絲案例仍未判出，沒有因為加速變好，也沒有變差。<b>正式流程、模型與設定未修改。</b></p></div>
<p>本次依要求只測同一張照片及既有案例，不是全圖資重新檢測。照片：{esc(full['base']['source_file'])}。所有版本都沿用前輪的參照資料重用，以及最新離線辨識方法；「原方法」指這個離線實驗基準，不是正式 r2。範例仍為47張螺絲＋65張正常，參照圖及待測圖都判斷。</p>
<h2 id="timing">各改一項，再全部合併：實際省多少？</h2><p>單位：秒。表中整段時間包含少量階段間整理；三次最小～最大值列在平均值下方。本輪基準與上次7.18秒不同，因此只用本次交錯重測結果相減。</p>
<div class="scroll"><table><tr><th>版本</th><th>整張對齊</th><th>差分找候選</th><th>局部修正＋舊版核對</th><th>整段平均<br><small>三次範圍</small></th><th>比本次原方法</th><th>候選及影像</th></tr>{rows}</table></div>
<h2>三項到底改了什麼？</h2><table><tr><th>項目</th><th>這次實際改法</th><th>受影響階段的實測差異</th></tr>
<tr><td>① 不同方向同時處理</td><td>每次同時準備、找特徵及比對2個方向；保留原本所有方向、7000個特徵與最佳結果選法。最後決定位置的順序仍相同。測過限制每工作1、4、8個底層執行緒，反而較慢；本輪用底層16執行緒。並非把8方向刪成2方向。</td><td>對齊 {baseline['register']:.2f} → {avg['align']['register']:.2f} 秒；{"省" if delta('align','register')>=0 else "慢"} {abs(delta('align','register')):.2f} 秒。</td></tr>
<tr><td>② 明暗計算減少中間資料</td><td>三輪校正及公式不變；重用暫存空間，把連續明暗計算分成短列區塊處理。第三輪後不再計算沒有下一輪會用到的資料。保留原有計算精度，校正及差異影像逐像素相同。</td><td>差分整段 {baseline['proposals']:.2f} → {avg['brightness']['proposals']:.2f} 秒；{"省" if delta('brightness','proposals')>=0 else "慢"} {abs(delta('brightness','proposals')):.2f} 秒。</td></tr>
<tr><td>③ 不同候選同時檢查</td><td>兩個候選可同時進行結構、周圍背景及線材核對；每個候選內的檢查順序、門檻不變，完成後依原來順序彙整。這次沒有改候選產生前面的所有工作，也沒有省略檢查。</td><td>差分整段 {baseline['proposals']:.2f} → {avg['candidates']['proposals']:.2f} 秒；{"省" if delta('candidates','proposals')>=0 else "慢"} {abs(delta('candidates','proposals')):.2f} 秒。</td></tr></table>
<p><b>對齊分工單獨測的平均幾乎沒有省，且三次波動大，不能稱為已穩定加速。</b>明暗校正與候選分工較有收益。合併結果是本輪量到的平均，不保證每張圖或每次執行都省同樣秒數。</p>
<p>分項節省不能直接相加：同一台CPU的分工與記憶體讀寫會互相影響。採用上面的合併實測值；這次沒有改DINO推論速度。</p>
<h2>實際從資料夾取圖，到 DINO 判完並存好結果</h2><p>原方法與合併方法各完整跑一次，使用CPU，含原本檔案穩定等待。這組用來確認整條流程與DINO結果；只有一次配對，總時間也會受DINO及系統負載波動影響，不能把所有秒數差異都算成這三項的功勞。</p>
<table><tr><th>時間範圍</th><th>原方法</th><th>三項合併</th><th>本次差異</th></tr>{fullrows}</table>
<p><b>{full_timing_note}</b></p>
<h2 id="proof">有沒有為了快，讓結果變了？</h2><table><tr><th>核對範圍</th><th>結果</th></tr>
<tr><td>同一張圖，5個版本各3次</td><td>137個候選的內容、座標與順序相同；對齊矩陣、對齊圖、局部修正圖、差異圖、39個舊版核對框與5處另列結構變化相同。</td></tr>
<tr><td>原方法與合併方法，各完整跑DINO一次</td><td>{proof['candidates']}個候選的兩圖判斷與保留／排除結果相同；DINO實際輸入相同；{proof['images']}張輸出圖片檔案內容相同。候選框數不等於螺絲顆數。</td></tr>
<tr><td>59個既有案例，來自{source['sources']}組影像</td><td>使用既有已對齊影像比較加速前後差分；共核對{totals}個保留候選，候選、明暗校正圖、差異圖全部相同。這部分沒有從原始圖重新驗證所有旋轉／鏡像方向。</td></tr>
<tr><td>59案例再實際跑CPU DINO</td><td>兩圖輸入及判斷相同；已判出的6處維持，包括原本兩顆與已救回的長螺絲；另外3處疑似螺絲仍未判出。42線材、2板件邊界、4元件外觀、2 U形結構，共50個正常案例仍零誤報。</td></tr>
<tr><td>正式程式、模型、設定、紀錄與本次原始圖</td><td>{preserved['files']}個受保護檔案內容未變。</td></tr></table>
<h2 id="cases">原本螺絲、線材、板件：59個案例全部保留供核對</h2><p>以下「原方法」使用前輪已核定的離線方法結果；「本次複驗」是本輪實際重新推論。圖片沿用並核對既有輸入，不另裁切或美化。</p>{casehtml}
<details><summary>展開15次交錯計時明細</summary><table><tr><th>次序</th><th>版本</th><th>對齊</th><th>差分</th><th>整段</th><th>輸出核對</th></tr>{perrun}</table></details>
<details><summary>原始紀錄與驗證檔案</summary><p><a href="timings.json">15次計時</a> · <a href="smoke.json">分工配置試測（含變慢結果）</a> · <a href="full-pipeline-verification.json">完整流程核對</a> · <a href="case-source-verification.json">案例來源核對</a> · <a href="dino-cases/cpu-summary.json">DINO複驗</a> · <a href="preservation-after.json">原檔保留核對</a></p></details></html>'''
    (OUT/'index.html').write_text(text,encoding='utf-8')
    class Links(HTMLParser):
        def __init__(self):super().__init__();self.paths=[]
        def handle_starttag(self,tag,attrs):
            for key,value in attrs:
                if key in ('href','src') and value and not value.startswith('#') and not urlparse(value).scheme:self.paths.append(value)
    parser=Links();parser.feed(text)
    missing=[p for p in parser.paths if not (OUT/unquote(p.split('#')[0])).exists()];assert not missing,missing
    summary=dict(averages=avg,saved_seconds=saved,saved_percent=saved/baseline['total']*100,full_pipeline={m:{k:full[m][k] for _,k in fields} for m in ('base','combined')},candidates=137,case_count=59,case_sources=source['sources'],case_candidate_checks=totals,dino_decision_changes=ai['decision_changes'],normal_false_alarms=ai['normal_false_alarms'],unchanged_unresolved_cases=[5,7,9],checked_links=len(parser.paths),formal_changes=False)
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
