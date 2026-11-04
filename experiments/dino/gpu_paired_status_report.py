"""Report failed GPU readiness without inventing full-photo timing results."""
import sys,json,datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'workspace/dino-gpu-paired-timing-20261104'
def load(n):return json.loads((OUT/n).read_text(encoding='utf-8'))
def main():
    status=load('status.json');samples=load('preflight.json');probe=load('short-probe.json');preserve=load('preservation-after.json')
    assert status['status']=='not_ready' and not preserve['changes']
    last=samples[-1]
    data=''.join(f'<tr><td>{i}</td><td>{datetime.datetime.fromtimestamp(s["wall"]).strftime("%H:%M:%S")}</td><td>{s["sm"]}</td><td>{s["current_limit"]}</td><td>{s["requested_limit"]}</td><td>{s["sw_thermal"]}</td><td>{s["sw_power"]}</td></tr>' for i,s in enumerate(samples,1))
    rows=''.join(f'<tr><td>{"參照小圖" if r["side"]=="reference" else "待測小圖"}</td><td>{r["seconds"]:.3f} 秒</td><td>{"有螺絲" if r["screw"] else "沒有螺絲"}</td><td>相同</td></tr>' for r in probe['rows'])
    text=f'''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GPU交錯比較：GPU限速，尚無有效全圖結果</title><style>body{{font:18px/1.7 'Microsoft JhengHei',sans-serif;color:#173e4c;background:#f5f8f9;max-width:1200px;margin:32px auto;padding:0 24px}}h1{{font-size:30px}}h2{{font-size:24px}}table{{width:100%;border-collapse:collapse;background:white;margin:20px 0}}td,th{{border:1px solid #d7e2e6;padding:12px;text-align:left}}th{{background:#e8f1f4}}.answer{{background:white;border-left:6px solid #b84a42;padding:20px}}a{{color:#007e8a}}details{{padding:18px;background:white}}</style>
<h1>GPU仍被限速：這次沒有正常GPU速度的交錯比較結果</h1><div class="answer"><p><b>7次檢查，GPU都維持300 MHz、10 W；功率及溫度限制標記持續作用。</b>要求的功率上限仍是80 W，不能把這個狀態當成正常GPU效能。</p><p><b>原方法與合併版的完整圖交錯測量尚未開始。</b>因此沒有「開始檢測到DINO出答案」的有效GPU秒數，也沒有本輪137個候選的完整GPU核對結果。</p><p>做了一組同張圖的螺絲對照小圖短測，GPU路徑可執行，這組兩圖判斷與CPU相同。正式流程、設定、模型、圖資與人工紀錄未改。</p></div>
<h2>目前可以與不能回答的項目</h2><table><tr><th>項目</th><th>本次結果</th></tr><tr><td>原方法：開始檢測→DINO判完</td><td>尚無有效GPU測量；限速檢查未通過。</td></tr><tr><td>合併版：開始檢測→DINO判完</td><td>尚無有效GPU測量；限速檢查未通過。</td></tr><tr><td>確認GPU沒有被限速</td><td>未通過。檢查及短測期間都觀察到限制。</td></tr><tr><td>候選框與DINO判斷是否維持</td><td>本輪只確認這組小圖的兩圖判斷相同；全圖137個候選沒有在本輪GPU重跑，不能宣稱已通過。</td></tr></table>
<h2>GPU實際狀態</h2><table><tr><th>顯示卡</th><td>{last['name']}</td></tr><tr><th>時脈／實際功率上限</th><td>{last['sm']}／{last['current_limit']}</td></tr><tr><th>要求功率上限</th><td>{last['requested_limit']}</td></tr><tr><th>溫度</th><td>{last['temperature']}</td></tr><tr><th>功率限制標記</th><td>{last['sw_power']}</td></tr><tr><th>溫度限制標記</th><td>{last['sw_thermal']}</td></tr></table>
<p>這些是本機顯示卡回報的狀態；溫度數字與限制標記本身不能確定最初觸發原因。沒有調整功率、時脈、驅動、效能設定，也沒有關閉其他應用程式。</p>
<h2>短測只確認GPU路徑與這組判斷</h2><p>使用同一張測試照片中，既有螺絲案例的參照與待測小圖。沿用47張螺絲＋65張正常範例及相同判斷方法，實際輸入雜湊與先前CPU紀錄相同。裝置：{probe['device']}；執行後端：DirectML。只執行兩張小圖，<b>下表不是一張完整X-RAY照片的檢測時間</b>。</p><table><tr><th>短測輸入</th><th>單次推論</th><th>DINO判斷</th><th>比CPU紀錄</th></tr>{rows}</table>
<p>短測監測取得{len(probe['samples'])}筆GPU狀態，其中{probe['constrained_samples']}筆仍受限。短測結束後，已結束本次建立的GPU工作程序。</p>
<details><summary>7次準備檢查明細</summary><table><tr><th>次序</th><th>時間</th><th>時脈</th><th>實際功率上限</th><th>要求上限</th><th>溫度限制</th><th>功率限制</th></tr>{data}</table></details>
<h2>後續重測的必要條件</h2><p>GPU必須先離開300 MHz／10 W的受限狀態。交錯測試程式已備妥：正常狀態下兩版各4次，分開資料夾等待，每次核對137個候選、DINO輸入、兩圖判斷與輸出圖片；測量期間每0.5秒記錄GPU狀態。若AI期間又受限，該次不作正常GPU速度比較。</p>
<p>受保護的{preserve['files']}個正式檔案內容未變。<a href="preflight.json">GPU準備檢查</a> · <a href="short-probe.json">短測與GPU狀態</a> · <a href="preservation-after.json">原檔保留核對</a> · <a href="status.json">本輪狀態</a></p></html>'''
    (OUT/'index.html').write_text(text,encoding='utf-8');print('Report generated: GPU not ready; no full-photo speed claim')
if __name__=='__main__':main()
