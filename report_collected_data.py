"""Render the local corpus experiment without modifying input images."""
import json
import html
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT=Path('workspace/windows-check/diagnostics/collected-data')
def read(path):return json.loads(path.read_text(encoding='utf-8'))

def main():
    baseline=[read(p) for p in (ROOT/'cache').glob('*/baseline.json')]
    reflected=[read(p) for p in (ROOT/'reflection').glob('*/result.json')]
    bank=read(ROOT/'normal-bank-experiment.json')
    font=ImageFont.truetype('C:/Windows/Fonts/msjh.ttc',18)
    sample=next(r for r in bank if r['relative'].startswith('MPT12/') and r['split']=='validation' and len(r['explained'])>=3)
    z=np.load(ROOT/'cache'/sample['sha256']/'aligned.npz')
    canvas=Image.new('RGB',(1000,780),'white');draw=ImageDraw.Draw(canvas)
    for row,c in enumerate(sample['explained'][:3]):
        identity=c['normal_variation_evidence'][0]['reference']
        normal=np.load(ROOT/'cache'/identity/'aligned.npz')['target']
        cx,cy=c['x']+c['w']//2,c['y']+c['h']//2
        x,y=max(0,cx-32),max(0,cy-32)
        for col,(name,arr) in enumerate([('原本參考良品',z['ref']),('驗證組良品（被誤報）',z['target']),('另一台已知良品',normal)]):
            tile=Image.fromarray(np.uint8(np.clip(arr[y:y+64,x:x+64],0,1)*255)).convert('RGB').resize((224,224))
            d=ImageDraw.Draw(tile);d.rectangle(((c['x']-x)*3.5,(c['y']-y)*3.5,(c['x']+c['w']-x)*3.5,(c['y']+c['h']-y)*3.5),outline='red',width=2)
            canvas.paste(tile,(col*330,row*260+30));draw.text((col*330,row*260),name,font=font,fill='black')
    canvas.save(ROOT/'normal-confirmation-examples.png')
    rows=[]
    for model in ['KPH33','MPT10','MPT11','MPT12']:
        rr=[r for r in baseline if r['model']==model];ok=[r for r in rr if 'count' in r]
        rows.append(f'<tr><td>{model}</td><td>{rr[0]["label"]}</td><td>{len(rr)}</td><td>{len(ok)}</td><td>{len(rr)-len(ok)}</td><td>{sum(r["count"] for r in ok)}</td></tr>')
    bankrows=[]
    for model in ['MPT10','MPT12']:
        for split in ['development','validation']:
            rr=[r for r in bank if r['relative'].startswith(model+'/') and r['split']==split]
            bankrows.append(f'<tr><td>{model}</td><td>{split}</td><td>{len(rr)}</td><td>{sum(r["before"] for r in rr)}</td><td>{sum(r["after"] for r in rr)}</td></tr>')
    details=''.join(f'<tr><td>{html.escape(r["relative"])}</td><td>{r.get("count","對齊失敗")}</td><td>{html.escape(r.get("error", ""))}</td></tr>' for r in sorted(baseline,key=lambda r:r['relative']))
    mirror=sum(bool(r.get('mirrored')) for r in reflected)
    injected=read(ROOT/'synthetic-retention.json')
    content=f'''<!doctype html><meta charset="utf-8"><title>X-Ray 圖資評估</title>
<style>body{{font:17px/1.7 sans-serif;max-width:1100px;margin:40px auto;color:#183641}}table{{border-collapse:collapse;width:100%;margin:20px 0}}td,th{{border:1px solid #ccd9dc;padding:8px;text-align:left}}img{{max-width:100%}}small{{color:#526872}}</style>
<h1>機種圖資評估與候選改善實驗</h1><p>2026-11-03 · 原方法 checkpoint：d99a1c6 · 固定差分門檻 0.13 · 候選數在 AI 分類前計算。</p>
<p>190 張不重複原始圖：MPT10 良品 90、MPT12 良品 50、KPH33 良品 2、MPT11 良品 1／不良品 47。扣除四張參考圖與指定暫放的 17_14_35_98.tiff，評估 185 張。原始圖資未修改。</p>
<h2>原方法基準</h2><table><tr><th>機種</th><th>標籤</th><th>測試數</th><th>成功</th><th>對齊失敗</th><th>成功影像候選總數</th></tr>{''.join(rows)}</table>
<p>對齊失敗不能算成零候選。OK/NG 是資料夾標籤；尚無完整物件框標註，不能計算真實螺絲 precision / recall。</p>
<h2>已接入 V8：鏡像方向檢查</h2><p>MPT11 有 {mirror} 張 TIFF 相對正常 PNG 呈鏡像方向。加入特徵點數、覆蓋率與相似度門檻後，46 張皆可進入比對，原先成功的 24 張保留原方向。標記可轉回原始照片座標；工程調教顯示「鏡像方向校正」。恢復比對的照片仍有大量候選，此改動不代表這些候選都是螺絲。</p>
<h2>實驗版：用其他良品確認正常差異</h2><p>每個機種最多選六個不同序號的開發組良品作比較庫，測試排除這些序號；依序號固定分開開發／驗證組。候選必須同時得到兩個獨立正常樣本的形狀、周圍結構與殘差支持，才另列為正常差異。未調低原方法敏感度。</p>
<table><tr><th>機種</th><th>組別</th><th>照片數</th><th>原候選</th><th>剩餘候選</th></tr>{''.join(bankrows)}</table>
<p>MPT12 驗證組減少 33.5%；MPT10 驗證組沒有改善。此功能尚未接入日常自動刪框，因這兩個機種沒有真實 NG 可驗證漏檢。MPT11 與 KPH33 沒有足夠不同良品建立比較庫。</p>
<p>人工注入物體測試：{len(injected)} 個，原方法找到 {sum(r['baseline_hit'] for r in injected)} 個，過濾後保留 {sum(r['retained'] for r in injected)} 個。這只驗證有限合成案例，不是真實 NG 準確率。</p>
<h2>被正常樣本解釋的候選</h2><p>{html.escape(sample['relative'])}；三列為三個候選。紅框為同一位置，第三欄只展示兩票支持中的一個樣本。可見單張參考圖與待測良品不同，但另一良品已有相同結構。</p><img src="normal-confirmation-examples.png">
<h2>逐張基準紀錄</h2><details><summary>展開 185 張結果</summary><table><tr><th>照片</th><th>原候選數</th><th>錯誤</th></tr>{details}</table></details>
<p>完整原始紀錄：benchmark-plan.json、cache/*/baseline.json、reflection/*/result.json、normal-bank-experiment.json、synthetic-retention.json。重跑入口：evaluate_collected_data.py、evaluate_reflection.py、experiment_normal_bank.py、verify_normal_variation.py。</p>'''
    (ROOT/'report.html').write_text(content,encoding='utf-8')
    print(ROOT/'report.html')

if __name__=='__main__':main()
