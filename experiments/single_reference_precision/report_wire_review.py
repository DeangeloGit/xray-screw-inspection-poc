"""Report review-order changes separately from candidate suppression."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from detector import prioritize

ROOT=Path('workspace/windows-check/diagnostics/collected-data')

def main():
    items=json.loads((ROOT/'remaining-56/index.json').read_text(encoding='utf-8'))
    evidence={r['number']:r['evidence'] for r in json.loads((ROOT/'wire-experiment.json').read_text())}
    checks=json.loads((ROOT/'wire-advisory-checks.json').read_text(encoding='utf-8'))
    previous=sum(not prioritize(r['candidate']) for r in items)
    current=sum(not prioritize(dict(r['candidate'],wire_review=evidence[r['number']])) for r in items)
    tagged=[r['number'] for r in items if evidence[r['number']]]
    assert len(items)==56 and previous==14 and current==6 and len(tagged)==15
    cards=''.join(f'<article><h3>#{n:02d} · 疑似線材位移，仍需複核</h3><a href="remaining-56-gallery.html#c{n}">查看位置與完整資料</a><img loading="lazy" src="remaining-56/{n:02d}.png"></article>' for n in tagged)
    total=len(checks['injections']);detected=sum(r['baseline_detected'] for r in checks['injections'])
    preserved=sum(r['retained'] for r in checks['injections']);unsafe=len(checks['unsafe_deletion_cases'])
    summary=dict(candidates_before=56,candidates_after=56,priority_before=previous,priority_after=current,
        wire_review_count=15,wire_review_numbers=tagged,synthetic_total=total,synthetic_detected=detected,synthetic_preserved=preserved,
        real_marked_regions=checks['real_regions_passed'],automatic_wire_deletion=False)
    (ROOT/'wire-review-summary.json').write_text(json.dumps(summary,indent=2))
    body=f'''<!doctype html><meta charset="utf-8"><title>V10 線材候選複核</title><style>body{{font:18px/1.7 sans-serif;max-width:1050px;margin:40px auto;color:#183641}}table{{width:100%;border-collapse:collapse}}td,th{{border:1px solid #ccd5db;padding:12px}}article{{padding:20px 0;border-bottom:1px solid #ccd5db}}img{{max-width:100%}}</style>
<h1>V10：線材位移的保守優先級判斷</h1><p>實際檢測仍只使用一張參照圖。正式功能只標記與排序，<strong>不刪除任何線材候選、不自動判定正常</strong>。MPT12 本次仍以 cnd64409qy.tiff 作離線參照；正式機型設定未更動。</p>
<table><tr><th>共同 48 張良品</th><th>V9</th><th>V10</th></tr><tr><td>全部候選</td><td>56</td><td>56（全數保留）</td></tr><tr><td>優先紅框</td><td>{previous}</td><td>{current}</td></tr><tr><td>黃色複核候選</td><td>{56-previous}</td><td>{56-current}</td></tr><tr><td>附線材位移提示</td><td>0</td><td>15</td></tr></table>
<p>15 個線材提示中有 8 個原本是優先紅框。這是減少優先警示干擾，不是把誤報數由 56 減至 41，也不代表偵測準確率提高 57%。使用者模式仍顯示並要求確認全部位置；工程模式有線材提示時預設展開其他候選。</p>
<h2>使用的證據</h2><p>候選位於長而細的連續線條、兩側能接回參照圖中同一條結構、原位置有線條消退、線寬與深淺在保守範圍內。深色零件邊角不使用這條規則。一般零件差異沒有可靠解釋時維持原判斷，沒有依座標忽略區域。</p>
<h2>為何不自動刪框</h2><p>測試在這些位置加入螺絲頭、小頭與細桿，涵蓋四種深淺。原型若拿線材提示直接刪除，會漏掉 {unsafe} 個較淡的小物體。因此正式版採用提示與排序，保留所有候選。</p>
<p>驗證：{total} 個合成案例，V9 找到 {detected} 個、V10 保留 {preserved} 個，候選座標與數量逐一比對相同；49 張原始 MPT12 測試圖的候選框也與 V9 完全相同。先前 8 個使用者標記的真實區域仍保留優先候選。合成測試不等於完整真實螺絲召回率，MPT12 尚缺真實 NG 標註。</p>
<h2>15 個提示的逐項對照</h2><p>編號沿用先前 56 個候選對照頁。</p>{cards}
<p>重跑：evaluate_wire.py、verify_wire.py、report_wire_review.py（位於 experiments/single_reference_precision）。</p>'''
    (ROOT/'wire-review-report.html').write_text(body,encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()
