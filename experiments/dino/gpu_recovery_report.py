"""Summarize the single-photo recovery measurement, not a dataset accuracy report."""
import html
import json
from pathlib import Path
from urllib.parse import quote, unquote
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'workspace/gpu-investigation-20261104'


def main():
    oldpath = ROOT / 'workspace/dino-folder-timing-20261103-222637-gpu-directml-prepared-once-fixed-shape/timing.json'
    cpupath = ROOT / 'workspace/dino-folder-timing-20261103-221347-cpu-prepared-once/timing.json'
    directpath = sorted((ROOT / 'workspace').glob('dino-folder-timing-20261104-*-gpu-directml-prepared-once-fixed-shape/timing.json'))[-1]
    workerpath = sorted((ROOT / 'workspace').glob('dino-folder-timing-20261104-*-gpu-worker-prepared-once-fixed-shape/timing.json'))[-1]
    def load(path):
        return json.loads(path.read_text(encoding='utf-8'))
    old, cpu, direct, new = map(load, (oldpath, cpupath, directpath, workerpath))
    ui = load(OUT / 'ui-gpu-verification.json')
    assert new['same_decisions_as_previous'] and not new['reference_target_decision_changes']
    assert new['protected_unchanged'] and new['candidates'] == 137 and new['retained'] == 19
    def href(path):
        import os
        return quote(Path(os.path.relpath(path, OUT)).as_posix())
    table = ''.join(f'<tr><td>{html.escape(s["name"])}</td><td>{s["seconds"]:.2f} 秒</td></tr>' for s in new['sections'])
    compare = ''.join(f'<tr><td>{name}</td><td>{d["total_seconds"]:.1f} 秒</td><td><a href="{href(path)}">原始時間紀錄</a></td></tr>'
        for name, d, path in [('前次 CPU（已減少重複影像準備）', cpu, cpupath), ('前次 GPU：受限 300 MHz／10 W', old, oldpath),
                             ('本次 GPU：直接呼叫', direct, directpath), ('本次 GPU：包含新選項使用的傳送路徑', new, workerpath)])
    document = f'''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GPU 恢復後，同一張照片要多久？</title><style>body{{font:19px/1.7 'Microsoft JhengHei',sans-serif;color:#173e4c;background:#f5f8f9;max-width:1150px;margin:35px auto;padding:0 24px}}h1{{font-size:32px}}h2{{font-size:25px;margin-top:38px}}.callout{{background:white;border-left:6px solid #00818c;padding:22px}}table{{border-collapse:collapse;width:100%;background:white}}td,th{{padding:13px;text-align:left;border:1px solid #d6e1e5}}th{{background:#e8f1f4}}a{{color:#007b87}}details{{background:white;padding:18px;margin:18px 0}}small{{font-size:16px}}</style>
<h1>GPU 恢復後，同一張照片約 {new['total_seconds']:.1f} 秒出結果</h1>
<p>2026-11-04 · 單張照片測速，不是全圖資辨識率報告。</p>
<div class="callout"><strong>從完整檔案出現在資料夾，到結果儲存並讀回：約 {new['total_seconds']:.1f} 秒。</strong><br>
取圖、等待與匯入約 {new['folder_to_analysis_seconds']:.1f} 秒；實際分析約 {new['analysis_seconds']:.1f} 秒。原本「檔案穩定等待 15 秒」沒有縮短。</div>
<h2>為什麼之前只有 300 MHz、10 W？</h2>
<p>先前的顯示卡紀錄同時顯示「功率限制」及「溫度限制」正在作用。當時要求的功率上限仍是 80 W，實際被壓到 10 W；這不是這次程式寫入的限制。</p>
<p><strong>今天開始檢查、尚未修改設定前，就已恢復為 80 W、945 MHz，兩項限制都未啟動。</strong>沒有調高功率、關閉保護、更新驅動或重開電腦。10 W／80 W 是當時的功率上限，不是每秒固定耗電量；945 MHz 也不是保證持續不變的時脈。</p>
<p>目前能確認「受到限制」及「現在已恢復」；尚不能確認最初由散熱、供電或筆電控制機制中的哪一項觸發。前後都曾讀到 79°C，因此不能只憑這個溫度就說散熱是唯一原因。Windows 本次查詢未找到相應的顯示卡／電源事件紀錄。</p>
<p><a href="{href(ROOT/'workspace/dino-speedup-20261103/gpu-state-during-test.txt')}">先前限速紀錄</a> · <a href="before.txt">本次修改前的紀錄</a> · <a href="after-initial-retest.txt">本次重測後的紀錄</a> · <a href="https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlClocksEventReasons.html">NVIDIA 對限制原因的說明</a></p>
<h2>相同照片的時間比較</h2><table><tr><th>測試方式</th><th>取圖到結果</th><th>證據</th></tr>{compare}</table>
<p>同一張 {html.escape(new['source_file'])}，同一張參照圖、同樣 47＋65 範例與雙圖規則。這些是單次測量，不是多次平均；掃描時機及電腦負載會讓秒數浮動。新 GPU 路徑與 CPU 的這兩次總時間相比，減少約 {(1-new['total_seconds']/cpu['total_seconds'])*100:.0f}%。</p>
<h2>這 {new['total_seconds']:.1f} 秒花在哪裡？</h2><table><tr><th>階段</th><th>耗時</th></tr>{table}<tr><th>合計</th><th>{new['total_seconds']:.2f} 秒</th></tr></table>
<p>模型與範例在取圖前已載入。這次測試的前置準備另花 {new['setup_seconds']:.2f} 秒，其中建立 GPU 連線／載入模型 {new['model_load_seconds']:.2f} 秒；不包含在上表。沒有排隊、網路共享資料夾延遲或瀏覽器畫面更新時間。</p>
<h2>變快後，有沒有改變判斷？</h2>
<p><strong>這張圖的 137 個候選，參照圖與待測圖的判斷全部一致，最後仍保留 19 框。</strong>19 是候選框數，不是確認有 19 顆螺絲。這次只驗證換計算設備不改答案，沒有重新宣稱辨識率。</p>
<p>另用原有 59 個案例驗證正式 r2 的 CPU／GPU 選項，兩邊判斷與最後決策也全部一致。切換失敗保留原設定、重新讀取保留選項、處理中的照片仍用原設備完成，皆已測過。<a href="ui-gpu-verification.json">查看驗證紀錄</a>。</p>
<h2>使用方式與版本範圍</h2>
<p>開啟 <a href="http://127.0.0.1:18766/settings?tab=ai">工程設定 → AI 模型 → DINO 執行方式</a>，選 CPU 或 GPU，再按「套用執行方式」。預設 CPU，套用成功後下一張分析使用新選擇，重啟後保留；舊照片不會自動重跑。</p>
<p><strong>上面的測速是這輪研究的改善方案，使用新 GPU 路徑完成的離線單張測試。</strong>本機正式辨識仍是原有 r2 雙圖、47＋65 範例；這次只加入設備選項，沒有將實驗辨識方法換入正式流程。正式版或其他照片的耗時不能直接當成這張的 {new['total_seconds']:.1f} 秒。既有可攜包本次沒有重新打包。</p>
<p>保留模型、設定、原始圖資與人工紀錄；沒有重跑整批。</p></html>'''
    document=document.replace('</html>', '<p><strong>本機載入狀態：</strong>18766 已載入 CPU／GPU 選項，目前仍選 CPU。最後補上的「重啟時 GPU 不可用，仍能切回 CPU」保護已通過隔離測試；最後一次重啟被自動核准檢查以「blocked by policy」拒絕，所以這項補強需下次手動重開程式才會載入。可關閉 X-RAY 程式後，執行專案內 start-windows.cmd。</p><details><summary>程式驗證範圍</summary><p>正式 r2：59 案例 CPU／GPU 雙邊判斷一致；工程頁面切換、設定保留、失敗保留原設定、進行中的照片不換設備，以及重啟時 GPU 不可用後切回 CPU 均通過測試。研究方案：同張照片 137 候選結果一致。另嘗試舊 verify_settings.py，但本機缺少該測試所需的 data/ok_0.png，未能執行；不宣稱整套舊測試全部通過。</p></details></html>')
    (OUT / 'index.html').write_text(document, encoding='utf-8')
    class Links(HTMLParser):
        def __init__(self):
            super().__init__(); self.links=[]
        def handle_starttag(self, tag, attrs):
            for k,v in attrs:
                if k in ('href','src') and not v.startswith(('http:', 'https:', '#')):
                    self.links.append(v)
    check=Links();check.feed(document)
    for link in check.links:
        assert (OUT/unquote(link)).exists(), link
    summary=dict(total_seconds=new['total_seconds'], analysis_seconds=new['analysis_seconds'],
        cpu_seconds=cpu['total_seconds'], throttled_gpu_seconds=old['total_seconds'],
        offline_137_unchanged=True, formal_59_unchanged=True, verified_links=len(check.links),
        root_trigger='not established; power and thermal limit flags were active, now inactive',
        measurement=str(workerpath))
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__ == '__main__':
    main()
