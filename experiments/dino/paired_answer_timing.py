"""Repeated full-path timing; measure the last DINO decision directly."""
import sys,json,subprocess,time,statistics,html,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
OUT=ROOT/'workspace/dino-paired-answer-timing-20261104'

def save(name,value):
    OUT.mkdir(exist_ok=True)
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))

def worker(mode):
    original=ROOT/'experiments/dino/folder_pipeline_timing.py'
    source=original.read_text(encoding='utf-8')
    needle=" for name in ['read','register','refine','proposals','legacy_proposals','write_image']:"
    assert source.count(needle)==1
    source=source.replace(needle,f" from experiments.dino.three_speed_pilot import ThreeSpeed\n three_speed=ThreeSpeed(detector,reuse,{mode!r},workers=2,inner_threads=16).install()\n"+needle)
    needle=" if args.cpu_reuse!='off':mode+='-cpu-reuse-'+args.cpu_reuse"
    assert source.count(needle)==1
    source=source.replace(needle,needle+"\n mode+='-answer-repeat-"+mode+"'")
    needle="input_hashes=dict(current_inputs)))"
    assert source.count(needle)==1
    source=source.replace(needle,"input_hashes=dict(current_inputs),completed_at=time.perf_counter()))")
    needle=" (OUT/'timing.json').write_text("
    assert source.count(needle)==1
    source=source.replace(needle," output['start_to_dino_answer_seconds']=max(c['completed_at'] for c in candidates)-origin-output['folder_to_analysis_seconds']\n output['after_dino_to_saved_seconds']=output['analysis_seconds']-output['start_to_dino_answer_seconds']\n"+needle)
    sys.argv=[str(original),'--prepare-once','--cpu-reuse','warm']
    exec(compile(source,str(original),'exec'),dict(__name__='__main__',__file__=str(original)))

def report(rows):
    means={m:{k:statistics.mean(r[k] for r in rows if r['mode']==m) for k in ('folder_to_analysis_seconds','start_to_dino_answer_seconds','analysis_seconds','after_dino_to_saved_seconds','ai_total','pre_ai_seconds','total_seconds')} for m in ('base','combined')}
    medians={m:statistics.median(r['start_to_dino_answer_seconds'] for r in rows if r['mode']==m) for m in means}
    difference=means['base']['start_to_dino_answer_seconds']-means['combined']['start_to_dino_answer_seconds']
    blocks=[]
    for i in range(0,len(rows),2):
        pair={r['mode']:r for r in rows[i:i+2]}
        blocks.append(pair['base']['start_to_dino_answer_seconds']-pair['combined']['start_to_dino_answer_seconds'])
    verdict=('本次合併版平均較快' if difference>0 else '本次合併版平均較慢')+f' {abs(difference):.2f} 秒'
    stable=all(d>0 for d in blocks)
    conclusion=('四組配對都較快。' if stable else f'四組配對中，{sum(d>0 for d in blocks)}組較快、{sum(d<=0 for d in blocks)}組較慢或相同；尚不能稱為穩定加速。')
    text=f'''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>排除資料夾等待：原方法與合併版交錯重測</title><style>body{{font:18px/1.7 'Microsoft JhengHei',sans-serif;color:#173e4c;background:#f5f8f9;max-width:1200px;margin:32px auto;padding:0 24px}}h1{{font-size:30px}}h2{{font-size:24px}}table{{border-collapse:collapse;width:100%;background:white;margin:20px 0}}td,th{{border:1px solid #d7e2e6;padding:12px;text-align:left}}th{{background:#e8f1f4}}.answer{{background:white;border-left:6px solid #00838c;padding:20px}}a{{color:#007e8a}}details{{background:white;padding:18px;margin-top:20px}}.images{{display:flex;gap:20px}}figure{{margin:0;flex:1}}img{{width:100%;max-height:500px;object-fit:contain}}</style>
<h1>不算資料夾等待：{verdict}</h1><div class="answer"><p><b>開始檢測 → 最後一個候選的 DINO 判斷完成：原方法 {means['base']['start_to_dino_answer_seconds']:.2f} 秒，合併版 {means['combined']['start_to_dino_answer_seconds']:.2f} 秒。</b></p><p>{conclusion}</p><p>同一張圖，原方法與合併版各4次，共8次。137個候選框、DINO兩圖判斷及保留／排除結果全部相同。正式流程、模型、設定及人工紀錄未修改。</p></div>
<h2>這次的時間從哪裡算？</h2><p>資料夾出現完成檔案 → <b>等待檔案穩定、掃描及匯入（另外列）</b> → <b>開始檢測【主計時起點】</b> → 讀圖、對齊、差分、準備小圖、依序判斷 → <b>最後一個候選的DINO判斷完成【主計時終點】</b> → 存完結果、讀回確認。</p><p>主計時直接記錄最後一次判斷完成時刻，沒有用整趟時間扣掉估計等待。程式原本會穿插儲存候選圖片，因此終點之前已做的儲存也包含在內；最後收尾另列。AI模型與參照資料已預先備妥，不含程式啟動／模型載入。兩版都使用CPU及同一套最新離線方法，47張螺絲＋65張正常範例、參照圖＋待測圖。</p>
<h2>分開看平均時間</h2><table><tr><th>範圍</th><th>原方法</th><th>合併版</th><th>差異</th></tr>'''
    labels=[('資料夾等待、掃描與匯入（排除於主計時）','folder_to_analysis_seconds'),('開始檢測 → DINO出答案（本次主要比較）','start_to_dino_answer_seconds'),('其中：DINO與小圖處理','ai_total'),('其中：對齊／差分／局部修正與核對','pre_ai_seconds'),('DINO完成 → 存好結果','after_dino_to_saved_seconds'),('開始檢測 → 存好結果','analysis_seconds'),('含資料夾等待的整趟時間（僅供參考）','total_seconds')]
    for label,k in labels:
        a,b=means['base'][k],means['combined'][k];d=a-b
        text+=f'<tr><td>{label}</td><td>{a:.2f} 秒</td><td>{b:.2f} 秒</td><td>{"省" if d>=0 else "慢"} {abs(d):.2f} 秒</td></tr>'
    text+='<table><tr><th>次序</th><th>版本</th><th>資料夾前段</th><th>開始檢測→DINO答案</th><th>開始檢測→存好</th><th>結果核對</th></tr>'
    for r in rows:
        text+=f'<tr><td>{r["run"]}</td><td>{"原方法" if r["mode"]=="base" else "合併版"}</td><td>{r["folder_to_analysis_seconds"]:.2f} 秒</td><td>{r["start_to_dino_answer_seconds"]:.2f} 秒</td><td>{r["analysis_seconds"]:.2f} 秒</td><td>137個候選及判斷相同</td></tr>'
    text+='</table><h2>每兩次為一組，合併版省多少？</h2><p>'+ '；'.join(f'第{i}組：{"省" if d>=0 else "慢"}{abs(d):.2f}秒' for i,d in enumerate(blocks,1))+'</p>'
    if difference<=0:
        text+=f'<p><b>這輪三項合併未通過加速驗證。</b>放進完整DINO流程後，對齊／差分等前段平均 {means["base"]["pre_ai_seconds"]:.2f} → {means["combined"]["pre_ai_seconds"]:.2f} 秒；AI與小圖處理平均 {means["base"]["ai_total"]:.2f} → {means["combined"]["ai_total"]:.2f} 秒。這輪能確認結果沒有變，無法認定合併方案讓整張更快出答案。</p>'
    text+=f'<p>中位數：原方法 {medians["base"]:.2f} 秒，合併版 {medians["combined"]:.2f} 秒。這是同一台電腦、同一張圖的CPU重測，不能推成GPU或其他圖資的耗時。這輪只驗證加速前後一致性，沒有重新宣稱辨識準確率提升。</p>'
    first=load(rows[0]['path']);imagefolder=Path(first['result_path']).parent
    def rel(p):return Path(os.path.relpath(p,OUT)).as_posix()
    text+='<h2>本次同一張圖</h2><div class="images">'
    for label,name in [('參照圖','reference.png'),('待測圖（已對齊）','aligned.png')]:
        assert (imagefolder/name).exists()
        text+=f'<figure><figcaption>{label}</figcaption><img src="{rel(imagefolder/name)}"></figure>'
    text+='</div><details><summary>完整核對與原始紀錄</summary><p>每次與本輪第1次比較：137個候選的內容、座標、順序、AI實際輸入、參照與待測的螺絲判斷及最終保留／排除都相同；每次368張輸出圖片檔案內容相同。候選數不代表螺絲顆數。</p><a href="runs.json">8次計時與逐次核對</a> · <a href="preservation-after.json">正式檔案保留核對</a></details></html>'
    text=text.replace('<table><tr><th>次序','</table><h2>8次交錯測量明細</h2><table><tr><th>次序')
    (OUT/'index.html').write_text(text,encoding='utf-8')
    summary=dict(means=means,medians=medians,saved_seconds=difference,saved_percent=difference/means['base']['start_to_dino_answer_seconds']*100,paired_savings=blocks,all_pairs_faster=stable,decision_changes=0,candidates=137,repetitions_per_mode=4,formal_changes=False)
    save('summary.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)

def main():
    from experiments.dino.three_speed_runs import preservation
    from experiments.dino.cpu_reuse_runs import compare
    before=preservation();save('preservation-before.json',before);rows=[];baseline=None
    # AB / BA / BA / AB balances order within each adjacent pair.
    for i,mode in enumerate(['base','combined','combined','base','combined','base','base','combined'],1):
        save('progress.json',dict(run=i,total=8,mode=mode));print(f'START {i}/8 {mode}',flush=True)
        existing=set((ROOT/'workspace').glob('dino-folder-timing-*/timing.json'))
        with (OUT/f'run-{i}-{mode}.log').open('w',encoding='utf-8') as log:
            p=subprocess.run([sys.executable,__file__,'--worker',mode],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=300)
        if p.returncode:raise RuntimeError(f'Run {i} failed; see log')
        created=set((ROOT/'workspace').glob('dino-folder-timing-*/timing.json'))-existing;assert len(created)==1
        path=created.pop();d=load(path)
        if baseline is None:baseline=d
        proof=compare(baseline,d)
        assert not d['reference_target_decision_changes'] and d['same_decisions_as_previous']
        row=dict(run=i,mode=mode,path=str(path),verification=proof)
        for k in ('folder_to_analysis_seconds','start_to_dino_answer_seconds','analysis_seconds','after_dino_to_saved_seconds','total_seconds'):row[k]=d[k]
        row['ai_total']=d['detector_stage_seconds']['ai_total'];row['pre_ai_seconds']=sum(d['detector_stage_seconds'][k] for k in ('register','proposals','legacy_proposals','refine'))
        rows.append(row);save('runs.json',rows)
        print(f'DONE {i}/8 {mode}: folder={row["folder_to_analysis_seconds"]:.2f}s, start-to-DINO={row["start_to_dino_answer_seconds"]:.2f}s; unchanged',flush=True)
    after=preservation();changes=[p for p,h in before.items() if after.get(p)!=h];assert not changes,changes
    save('preservation-after.json',dict(files=len(before),changes=changes));report(rows);save('progress.json',dict(status='complete'))

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--worker':worker(sys.argv[2])
    else:main()
