"""Add the verified idle-close condition to the eight-run timing report."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.dino import paired_answer_timing as report
OUT=ROOT/'workspace/dino-after-portable-close-20261104'
def main():
    report.OUT=OUT;report.report(report.load(OUT/'runs.json'))
    evidence=report.load(OUT/'portable-close-evidence.json');assert evidence['closed']
    p=OUT/'index.html';text=p.read_text(encoding='utf-8')
    condition='''<h2>這次已先排除另一個可攜版</h2><p>可攜版原本在反覆重試一張對齊失敗的舊圖。本次先等它回到等待空檔，確認沒有處理中／待處理項目，且連續三次CPU低用量，才關閉PID 3244。啟動器也已退出，8766不再提供服務；本機18766保留運作。關閉時資料庫仍有11筆完成、1筆錯誤，設定及原有紀錄保留。</p><p>本頁只比較關閉後、同一張圖的8次結果。其他背景程式未停止，因此仍可能有一般系統波動；不把前一輪與本輪的時間差全算成關閉程序的效果。</p><p><a href="portable-close-evidence.json">關閉前的狀態與CPU檢查紀錄</a></p>'''
    text=text.replace('<h1>不算資料夾等待：','<h1>關閉另一個可攜版後，排除資料夾等待：')
    text=text.replace('<h2>這次的時間從哪裡算？</h2>',condition+'<h2>這次的時間從哪裡算？</h2>')
    p.write_text(text,encoding='utf-8')
    summary=report.load(OUT/'summary.json');summary.update(portable_closed_before_runs=True,old_portable_pid=3244)
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
