"""Estimate only: replace CPU portions, retain historical healthy GPU timings."""
import json,statistics,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'workspace/dino-gpu-optimized-estimate-20261104'
def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def main():
    cpu=ROOT/'workspace/dino-after-portable-close-20261104'
    means=load(cpu/'summary.json')['means']['combined'];runs=load(cpu/'runs.json')
    read=statistics.mean(load(r['path'])['detector_stage_seconds']['read'] for r in runs if r['mode']=='combined')
    rows=[]
    for prefix in ['071412','072634','072718']:
        paths=list((ROOT/'workspace').glob(f'dino-folder-timing-20261104-{prefix}*/timing.json'));assert len(paths)==1
        p=paths[0];d=load(p);s=d['detector_stage_seconds']
        pre=sum(s[k] for k in ('register','refine','proposals','legacy_proposals'))
        other=d['analysis_seconds']-pre-s['read']-s['ai_total']
        predicted=means['pre_ai_seconds']+read+s['ai_total']+other
        rows.append(dict(source=str(p),previous_analysis_seconds=d['analysis_seconds'],new_cpu_pre_seconds=means['pre_ai_seconds'],new_read_seconds=read,unchanged_historical_ai_seconds=s['ai_total'],unchanged_other_seconds=other,estimated_start_to_saved_seconds=predicted))
    best=min(rows,key=lambda r:r['estimated_start_to_saved_seconds'])
    summary=dict(estimate_only=True,scope='Same photo; model/reference ready; excludes folder waiting; includes saving',best=best,scenarios=rows,not_a_new_gpu_measurement=True,formal_changes=False)
    OUT.mkdir(exist_ok=True);(OUT/'estimate.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    rel=lambda p:Path(os.path.relpath(p,OUT)).as_posix()
    comparisons=''.join(f'<tr><td><a href="{rel(r["source"])}">正常GPU紀錄 {i}</a></td><td>{r["previous_analysis_seconds"]:.2f} 秒</td><td>{r["estimated_start_to_saved_seconds"]:.2f} 秒</td></tr>' for i,r in enumerate(rows,1))
    text=f'''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>優化版正常GPU時間估算</title><style>body{{font:19px/1.7 'Microsoft JhengHei',sans-serif;color:#173e4c;background:#f5f8f9;max-width:1100px;margin:32px auto;padding:0 24px}}h1{{font-size:30px}}h2{{font-size:24px}}.answer{{background:white;border-left:6px solid #00838c;padding:22px}}table{{width:100%;border-collapse:collapse;background:white;margin:22px 0}}td,th{{border:1px solid #d7e2e6;padding:12px;text-align:left}}th{{background:#e8f1f4}}a{{color:#007e8a}}</style>
<h1>同一張圖：正常GPU的優化版，最佳估約13秒出結果</h1><div class="answer"><p><b>最佳估算 {best['estimated_start_to_saved_seconds']:.2f} 秒，約13秒。</b>從開始檢測到存好結果，排除資料夾等待，模型與參照資料已載入。這是依舊的正常GPU實測與本次CPU分段實測推算，尚未完成正常GPU的合併版全流程重測。</p><p>另外兩筆正常GPU紀錄推算約14.5～14.7秒。因此這張圖可先抓<b>13～15秒</b>作估算範圍，不是所有照片的保證時間。</p></div>
<h2>13秒怎麼算？</h2><table><tr><th>項目</th><th>時間</th><th>來源</th></tr><tr><td>優化後的對齊、差分、局部修正與核對</td><td>{best['new_cpu_pre_seconds']:.2f} 秒</td><td>本次關閉干擾程式後，合併版四次CPU測量的平均。</td></tr><tr><td>GPU DINO、準備小圖與範例比較</td><td>{best['unchanged_historical_ai_seconds']:.2f} 秒</td><td>沿用上次正常GPU較快的一筆完整實測，沒有假設DINO會再加速。</td></tr><tr><td>讀圖、儲存與其他整理</td><td>{best['new_read_seconds']+best['unchanged_other_seconds']:.2f} 秒</td><td>讀圖用本次合併版平均；其他工作保留該筆正常GPU實測的耗時。</td></tr><tr><th>合計</th><th>{best['estimated_start_to_saved_seconds']:.2f} 秒</th><td>這是估算，不是本輪GPU實測。</td></tr></table>
<p>計算方式是替換對應階段：舊完整時間 − 舊對齊差分等前段 − 舊讀圖 + 新前段 + 新讀圖。沒有重複扣除先前CPU重用的節省，也沒有把整段CPU的加速百分比套到GPU推論。</p>
<h2>三筆正常GPU紀錄分別推算</h2><table><tr><th>來源</th><th>原本開始檢測→存好</th><th>替換成新前段後（估算）</th></tr>{comparisons}</table>
<p>DINO判完早於結果存好；舊紀錄沒有本輪新增的精準DINO終點時間，因此這裡保留包含儲存的口徑，不另捏造純粹「到最後一次判斷」的秒數。若仍維持目前資料夾等待與匯入約19秒，最佳情境取圖到存好約32秒；資料夾前段會受掃描時點影響。</p>
<p>只用同一張MPT12照片與既有紀錄作估算；未重跑檢測、未修改正式流程、模型、範例、設定或人工紀錄。完整GPU合併版的候選／判斷一致性仍待GPU正常後驗證，不能由此估算宣稱已通過。</p>
<p><a href="estimate.json">計算明細</a> · <a href="{rel(cpu/'index.html')}">本次CPU分段測量</a></p></html>'''
    (OUT/'index.html').write_text(text,encoding='utf-8');print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
