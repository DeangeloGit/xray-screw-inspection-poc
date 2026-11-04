"""Report measured CPU activity and the shutdown intervention separately."""
import json,statistics,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'workspace/dino-ai-contention-20261104'
def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def main():
    rows=load(OUT/'runs.json');assert len(rows)==6
    names={'base':'原方法','combined':'合併版：保留分工','closed':'合併版：AI前關閉分工'}
    means={m:{k:statistics.mean(r[k] for r in rows if r['mode']==m) for k in ('ai','answer')} for m in names}
    groups=[{r['mode']:r for r in rows[:3]},{r['mode']:r for r in rows[3:]}]
    close_effects=[g['combined']['ai']-g['closed']['ai'] for g in groups]
    combo_effects=[g['base']['ai']-g['combined']['ai'] for g in groups]
    poolmax=max(r['audit']['groups']['python_pool']['cpu_seconds'] for r in rows)
    othermax=max(r['audit']['groups']['other_threads']['cpu_seconds'] for r in rows)
    no_busy=poolmax<.03 and othermax<.5
    closure_consistent=all(x>0 for x in close_effects)
    title='沒有量到前段分工持續搶CPU；耗時差異較符合測試波動' if no_busy and not closure_consistent else '關閉分工的效果，與CPU實際用量分開看'
    if no_busy:
        evidence=f'前段新增的兩個工作，在AI開始後沒有量到可見的CPU運算時間（記錄為 {poolmax:.2f} 秒）。其他前段工作最多只用 {othermax:.2f} 個CPU秒，沒有量到持續搶CPU。'
    else:evidence=f'分工執行緒CPU時間最多 {poolmax:.3f} 秒，其他工作執行緒最多 {othermax:.3f} 秒；需配合關閉對照，不能只由執行緒數量判斷是否搶CPU。'
    direction=lambda x:f'{"快" if x>0 else "慢"} {abs(x):.2f} 秒'
    interpretation=('關閉分工沒有兩次都變快，無法把前輪AI較慢歸因於分工互搶CPU。' if not closure_consistent else '關閉分工兩次都較快，但CPU用量仍需一起看；這兩組對照不足以單獨證明原因。')
    details=''
    for r in rows:
        a=r['audit'];external=a['external_busy_core_seconds']/a['wall_seconds']
        details+=f'<tr><td>{r["run"]}</td><td>{names[r["mode"]]}</td><td>{r["ai"]:.2f}</td><td>{r["answer"]:.2f}</td><td>{a["groups"]["python_pool"]["cpu_seconds"]:.3f}</td><td>{a["groups"]["other_threads"]["cpu_seconds"]:.3f}</td><td>{external:.2f} 核心</td><td>相同</td></tr>'
    summaryrows=''
    for m,name in names.items():
        vals=[r['ai'] for r in rows if r['mode']==m]
        summaryrows+=f'<tr><td>{name}</td><td>{means[m]["ai"]:.2f} 秒</td><td>{min(vals):.2f}～{max(vals):.2f} 秒</td><td>{means[m]["answer"]:.2f} 秒</td></tr>'
    full=load(rows[0]['path']);folder=Path(full['result_path']).parent
    rel=lambda p:Path(os.path.relpath(p,OUT)).as_posix()
    text=f'''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AI變慢原因：分工互搶，還是測試波動？</title><style>body{{font:18px/1.7 'Microsoft JhengHei',sans-serif;color:#173e4c;background:#f5f8f9;max-width:1200px;margin:32px auto;padding:0 24px}}h1{{font-size:30px}}h2{{font-size:24px;margin-top:30px}}table{{border-collapse:collapse;width:100%;background:white;margin:20px 0}}td,th{{border:1px solid #d7e2e6;padding:12px;text-align:left}}th{{background:#e8f1f4}}.answer{{background:white;border-left:6px solid #00838c;padding:20px}}a{{color:#007e8a}}details{{background:white;padding:18px;margin-top:20px}}.images{{display:flex;gap:20px}}figure{{margin:0;flex:1}}img{{width:100%;max-height:450px;object-fit:contain}}</style>
<h1>{title}</h1><div class="answer"><p><b>{evidence}</b></p><p>合併版在AI前關閉分工：第一組{direction(close_effects[0])}，第二組{direction(close_effects[1])}。{interpretation}</p><p><b>同一張圖，三種版本各兩次，共6次；137個候選框、DINO實際輸入及兩圖判斷全部相同。正式流程沒有改。</b></p></div>
<h2>三種版本只差在哪裡？</h2><table><tr><th>版本</th><th>目的</th></tr><tr><td>原方法</td><td>沒有新增前段分工，作為對照。</td></tr><tr><td>合併版：保留分工</td><td>與前輪合併版相同，前段結束後，分工執行緒仍存在。</td></tr><tr><td>合併版：AI前關閉分工</td><td>完成同樣前段、得到同樣候選後，先結束新增的兩個分工執行緒，再跑相同AI。沒有調AI核心數、模型、範例或判斷門檻，也沒有更改OpenCV核心設定。</td></tr></table>
<p>順序：原方法 → 合併版 → 關閉分工版 → 關閉分工版 → 合併版 → 原方法。兩組順序相反，避免總是先跑某版。本次均使用CPU、同一套最新離線辨識方法及47張螺絲＋65張正常範例，參照圖與待測圖都判斷。各次使用獨立程序、預先載入模型與參照資料；資料夾等待不算進以下兩個時間。</p>
<h2>AI耗時與完整出答案時間</h2><table><tr><th>版本</th><th>AI與小圖處理平均</th><th>兩次最快～最慢</th><th>開始檢測→DINO判完平均</th></tr>{summaryrows}</table>
<p>「AI與小圖處理」包含準備輸入、DINO看兩圖、範例比較及必要補查；「開始檢測→DINO判完」另外包含讀圖、對齊、差分及之前穿插的圖片儲存。兩者都排除資料夾等待。</p>
<h2>執行緒還存在，不代表它還在忙</h2><p>使用Windows實際工作執行緒CPU時間，直接比較AI前後的累積值。若某工作真的佔用一個CPU核心10秒，會增加約10秒CPU時間。這次觀察從AI開始到結果存好，含最後的儲存收尾，統計範圍稍大於純AI時間。</p><p>記錄為0.000秒表示低於系統CPU計時粒度，不能理解成數學上的絕對零。模型準備階段建立的工作執行緒（包含數值運算套件）歸在另一組；主執行緒也另外計，不把DINO自己需要的CPU誤算成前段競爭。</p>
<table><tr><th>次序</th><th>版本</th><th>AI秒數</th><th>開始→答案</th><th>新增分工CPU秒</th><th>其他工作CPU秒</th><th>其他程式平均CPU用量</th><th>結果</th></tr>{details}</table>
<p>「其他程式平均CPU用量」用全機忙碌CPU時間扣除本次程序CPU時間估算，單位是核心數；包含系統工作，沒有指認哪個程式，也不能單靠它確定速度波動原因。</p>
<h2>可以下什麼結論？</h2><p>原方法對比合併版：第一組合併版{direction(combo_effects[0])}，第二組{direction(combo_effects[1])}。{interpretation}</p><p>這輪可以檢查「分工執行緒仍在搶CPU」的說法；不能排除CPU時脈、溫度、背景工作、記憶體快取或其他先前工作留下的影響。這些原因沒有被本輪逐項控制，不能把其中一個寫成已查明。若本次差異隨先後順序改變且關閉分工沒有固定收益，應視為目前沒有證據支持持續互搶，而不是宣稱所有差異都已找到原因。</p>
<h2>同一張測試圖</h2><div class="images"><figure>參照圖<img src="{rel(folder/'reference.png')}"></figure><figure>待測圖（已對齊）<img src="{rel(folder/'aligned.png')}"></figure></div>
<details><summary>核對與完整紀錄</summary><p>6次皆與第1次比對：137個候選的內容、位置與順序相同；DINO輸入、參照與待測的螺絲判斷、最終保留／排除相同；各次368張輸出圖片相同。候選數不代表螺絲數。本次只重測這張圖，沒有重跑全圖資。</p><a href="runs.json">6次計時、執行緒用量與核對</a> · <a href="preservation-after.json">正式檔案保留核對</a></details></html>'''
    observed=load(OUT/'old-portable-cpu-confirmation.json')
    background=f'''<h2>另外找到的實際干擾來源</h2><p><b>另一個可攜版 XRayReview（PID 3244）同時在用CPU。</b>程式來自 AppData\\Local\\XRayReview\\versions\\cpu-7de80f4925b7e0c5。先前全程序粗測估計約4.8個核心；再用該程序的Windows CPU累積時間精確讀取，{observed['elapsed_seconds']:.2f}秒內用了{observed['cpu_seconds']:.2f}個CPU秒，平均約<b>{observed['average_busy_cores']:.2f}個核心</b>。這證明有其他XRayReview程序佔用CPU，且短測負載不同。</p><p>沒有停止或暫停這個程序，也沒有更動它的設定、CPU分配或工作。因為沒有做停用前後的隔離對照，不能說它就是全部差異的唯一原因，或把某個秒數直接歸給它；但目前明確存在外部負載干擾，不能把這些測試當成空閒電腦上的速度比較。</p><p><a href="old-portable-process.json">程序路徑</a> · <a href="old-portable-cpu-confirmation.json">CPU實測</a></p>'''
    text=text.replace('<h2>可以下什麼結論？</h2>',background+'<h2>可以下什麼結論？</h2>')
    text=text.replace('耗時差異較符合測試波動','耗時差異較符合外部負載與執行速度波動')
    text=text.replace('</div>','<p>另外查到另一個可攜版XRayReview程式同時佔用CPU。本輪不是在空閒電腦上測量；外部負載確實存在，但尚未做停用前後對照，不能認定它是唯一原因。</p></div>',1)
    (OUT/'index.html').write_text(text,encoding='utf-8')
    summary=dict(means=means,close_effects_seconds=close_effects,combo_effects_seconds=combo_effects,max_pool_cpu_seconds=poolmax,max_other_thread_cpu_seconds=othermax,no_sustained_competing_cpu_observed=no_busy,closure_consistently_faster=closure_consistent,decision_changes=0,formal_changes=False)
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
