"""Plain-language report for a fresh GPU repeat, including unsuccessful runs."""
import html
import json
import os
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from experiments.dino.gpu_paired_timing import constrained


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def main(folder):
    folder = Path(folder).resolve()
    status = load(folder / 'status.json')
    runs = load(folder / 'runs.json') if (folder / 'runs.json').exists() else []
    rows, active_samples, sampling_intervals = [], [], []
    for run in runs:
        d = load(run['path'])
        row = dict(run=run['run'], mode=run['mode'], valid=run['limited_samples'] == 0)
        for key in ('folder_to_analysis_seconds', 'start_to_dino_answer_seconds', 'analysis_seconds',
                    'after_dino_to_saved_seconds', 'total_seconds'):
            row[key] = d[key]
        row['ai_total'] = d['detector_stage_seconds']['ai_total']
        row['pre_ai_seconds'] = sum(d['detector_stage_seconds'][key] for key in ('register','proposals','legacy_proposals','refine'))
        row['read'] = d['detector_stage_seconds']['read']
        row['write_image'] = d['detector_stage_seconds']['write_image']
        row['gpu_inference'] = sum(value for key,value in d['ai_stage_seconds'].items() if key.endswith('_inference'))
        row['counts'] = d['counts']
        row['verification'] = run['verification']
        row['cpu_verification'] = run['cpu_verification']
        row['provider'] = d['provider']
        row['gpu_adapter'] = d['gpu_adapter']
        intervals = [(c['completed_at'] - c['seconds'], c['completed_at']) for c in d['candidate_timings']]
        samples = load(folder / f'gpu-samples-{run["run"]}.json')
        sampling_intervals.extend(b['monotonic']-a['monotonic'] for a,b in zip(samples,samples[1:]) if 'monotonic' in a and 'monotonic' in b)
        active = [s for s in samples if any(a <= s.get('monotonic',0) <= b for a,b in intervals)]
        assert len(active) == run['gpu_samples']
        assert sum(constrained(s) for s in active) == run['limited_samples']
        active_samples.extend(active)
        assert row['provider'] == 'DmlExecutionProvider'
        for proof in (row['verification'], row['cpu_verification']):
            assert proof['candidates'] == 137 and proof['images'] == 368
            assert not any(proof[k] for k in ('registration_or_audit_changes','candidate_changes','decision_changes','dino_input_changes','image_changes'))
        rows.append(row)
    complete = status['status'] == 'complete' and len(rows) == 8 and all(r['valid'] for r in rows)
    summary = dict(status=status, full_comparison_complete=complete, runs=rows, formal_changes=False)
    body = '<h1>GPU：原方法與合併優化版，重新實測</h1>'
    if complete:
        keys = ('folder_to_analysis_seconds','start_to_dino_answer_seconds','analysis_seconds','after_dino_to_saved_seconds',
                'total_seconds','ai_total','pre_ai_seconds','read','write_image','gpu_inference')
        means = {m:{k:statistics.mean(r[k] for r in rows if r['mode']==m) for k in keys} for m in ('base','combined')}
        paired = []
        for i in range(0,8,2):
            pair = {r['mode']:r for r in rows[i:i+2]}
            paired.append(pair['base']['start_to_dino_answer_seconds'] - pair['combined']['start_to_dino_answer_seconds'])
        saved = means['base']['start_to_dino_answer_seconds'] - means['combined']['start_to_dino_answer_seconds']
        summary.update(means=means, paired_savings=paired, saved_seconds=saved,
                       saved_percent=saved/means['base']['start_to_dino_answer_seconds']*100)
        body += f'<div class="answer"><p><b>從開始檢測到 DINO 判完：原方法 {means["base"]["start_to_dino_answer_seconds"]:.2f} 秒，合併版 {means["combined"]["start_to_dino_answer_seconds"]:.2f} 秒。</b></p>'
        body += f'<p>合併版平均{"省" if saved>=0 else "慢"} {abs(saved):.2f} 秒（{abs(summary["saved_percent"]):.1f}%）。四組相鄰比較中，{sum(v>0 for v in paired)} 組較快、{sum(v<=0 for v in paired)} 組較慢或相同。</p>'
        body += '<p>各跑 4 次，共 8 次；137 個候選框、DINO 實際收到的小圖、參照／待測判斷、保留／排除結果及 368 張輸出圖片，全部一致，也與先前 CPU 紀錄一致。</p></div>'
        body += '<h2>各階段平均耗時</h2><table><tr><th>工作</th><th>原方法 GPU</th><th>合併版 GPU</th><th>合併版差異</th></tr>'
        for title,key in [('開始檢測 → DINO 判完（主比較）','start_to_dino_answer_seconds'),
                          ('其中：讀圖','read'),('其中：對齊、差分與局部核對','pre_ai_seconds'),
                          ('其中：DINO 判斷與準備小圖','ai_total'),('其中：GPU 推論呼叫','gpu_inference'),
                          ('DINO 判完 → 結果存好','after_dino_to_saved_seconds'),('開始檢測 → 結果存好','analysis_seconds'),
                          ('資料夾等待、掃描與匯入（另計）','folder_to_analysis_seconds'),('含資料夾前段的整趟時間','total_seconds')]:
            a,b=means['base'][key],means['combined'][key]
            body += f'<tr><td>{title}</td><td>{a:.2f} 秒</td><td>{b:.2f} 秒</td><td>{"省" if a>=b else "慢"} {abs(a-b):.2f} 秒</td></tr>'
        body += '</table><p>「其中」各列有包含關係，不能全部相加。GPU 推論呼叫包含程序間傳輸及等待，不是只有顯示卡晶片運算。</p>'
        cpu=load(ROOT/'workspace/dino-after-portable-close-20261104/summary.json')['means']
        body += f'<h2>與上次 CPU 時間對照</h2><p>同一張圖的舊 CPU 紀錄：原方法 {cpu["base"]["start_to_dino_answer_seconds"]:.2f} 秒、合併版 {cpu["combined"]["start_to_dino_answer_seconds"]:.2f} 秒。這次 GPU 合併版為 {means["combined"]["start_to_dino_answer_seconds"]:.2f} 秒。CPU 是先前測量，並非這輪同時交錯的比較；這輪可直接比較的是兩種 GPU 方法。</p>'
    else:
        body += '<div class="answer"><p><b>本輪沒有完成正常 GPU 狀態下的 8 次比較。</b></p><p>以下保留實際測到的紀錄；不把受限或未完成的結果當成正常 GPU 效能結論。</p></div>'
        body += '<p>狀態：' + html.escape(json.dumps(status,ensure_ascii=False)) + '</p>'
    if active_samples:
        def nums(key):return [float(s[key].split()[0]) for s in active_samples]
        sm,power,temp,draw=nums('sm'),nums('current_limit'),nums('temperature'),nums('draw')
        limits=sum(constrained(s) for s in active_samples)
        summary['gpu_monitor']=dict(ai_samples=len(active_samples),limited_samples=limits,sm_range=[min(sm),max(sm)],
                                    median_sample_interval_seconds=statistics.median(sampling_intervals),
                                    power_limit_range=[min(power),max(power)],temperature_range=[min(temp),max(temp)],draw_range=[min(draw),max(draw)])
        body += f'<h2>GPU 運算時有沒有再限速？</h2><p>DINO 處理期間取得 {len(active_samples)} 筆 GPU 狀態，{limits} 筆出現本輪檢查的異常限制。運算時脈 {min(sm):.0f}～{max(sm):.0f} MHz；功率上限 {min(power):.0f}～{max(power):.0f} W；實際耗電 {min(draw):.1f}～{max(draw):.1f} W；溫度 {min(temp):.0f}～{max(temp):.0f}°C。</p>'
        body += f'<p>實際抽查間隔的中位數為 {statistics.median(sampling_intervals):.2f} 秒（每筆查詢完成後等待 0.5 秒再查）。檢查溫度降速、硬體降速，以及實際功率上限是否明顯低於要求的 80 W；一般碰到原廠功率上限不直接算異常。這是抽查紀錄，不能保證兩次抽查間完全沒有短暫波動。待機時 300 MHz 本身不代表異常限速。</p>'
    if rows:
        body += '<h2>8 次交錯紀錄</h2><table><tr><th>次序</th><th>方法</th><th>開始檢測 → DINO 判完</th><th>開始檢測 → 存好</th><th>GPU 狀態</th></tr>'
        for r in rows:
            body+=f'<tr><td>{r["run"]}</td><td>{"原方法" if r["mode"]=="base" else "合併版"}</td><td>{r["start_to_dino_answer_seconds"]:.2f} 秒</td><td>{r["analysis_seconds"]:.2f} 秒</td><td>{"通過" if r["valid"] else "受限，本次無效"}</td></tr>'
        body+='</table>'
        if complete:body+='<p>四組合併版節省時間：'+'、'.join(f'{v:.2f} 秒' for v in summary['paired_savings'])+'；負數代表變慢。</p>'
        first=load(runs[0]['path']);imagefolder=Path(first['result_path']).parent
        body+='<h2>同一張參照／待測圖</h2><div class="images">'
        for title,name in [('參照圖','reference.png'),('待測圖（已對齊）','aligned.png')]:
            path=imagefolder/name;assert path.is_file()
            body+=f'<figure><figcaption>{title}</figcaption><img src="{Path(os.path.relpath(path,folder)).as_posix()}"></figure>'
        body+='</div>'
    preserve=load(folder/'preservation-after.json');assert not preserve['changes']
    body+='<h2>這次的範圍與計時方式</h2><p>只重測既有 MPT12 同一張圖。DINO 使用 47 張螺絲＋65 張正常範例、同時判斷參照圖和待測圖；兩版採用同一套最新離線辨識方法，只比較三項 CPU 前處理加速合併前後的差異。「原方法」指本次速度比較的基準，不等同正式 r2 辨識結果。</p><p>模型、範例特徵與參照資料預先備妥；主計時從開始檢測，直接量到最後一個候選的 DINO 判斷完成。終點之前穿插的圖片儲存包含在內；完成後儲存收尾另列。資料夾等待也另外列出。不包含程式啟動、排隊或瀏覽器畫面更新。候選數不是螺絲顆數，本次確認結果一致，不代表重新證明辨識準確率。</p>'
    body+=f'<p>正式程式、設定、模型、圖資及人工紀錄沒有更動；{preserve["files"]} 個受保護檔案核對通過。未啟動或重啟本機服務，未改顯示卡設定，也未關閉其他應用程式。</p>'
    body+='<p><a href="summary.json">統計與核對紀錄</a> · <a href="preflight.json">GPU 測前狀態</a> · <a href="preservation-after.json">正式檔案保留核對</a> · <a href="status.json">完成狀態</a></p>'
    style="body{font:18px/1.7 'Microsoft JhengHei',sans-serif;color:#173e4c;background:#f5f8f9;max-width:1200px;margin:32px auto;padding:0 24px}h1{font-size:30px}h2{font-size:24px}table{width:100%;border-collapse:collapse;background:white;margin:20px 0}td,th{border:1px solid #d7e2e6;padding:12px;text-align:left}th{background:#e8f1f4}.answer{background:white;border-left:6px solid #00838c;padding:20px}.images{display:flex;gap:20px}figure{margin:0;flex:1}img{width:100%;max-height:540px;object-fit:contain}a{color:#007e8a}"
    (folder/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    (folder/'index.html').write_text('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GPU 重測：原方法與合併版</title><style>'+style+'</style>'+body+'</html>',encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k!='runs'},ensure_ascii=False,indent=2))


if __name__=='__main__':main(sys.argv[1])
