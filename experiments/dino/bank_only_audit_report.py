"""Keep the verified full corpus; attach rejected bank-only trials transparently."""
import sys,json,shutil,hashlib,re
from pathlib import Path
from collections import Counter
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
EXP=ROOT/'workspace/dino-4r-bank-only-20261106';OUT=EXP/'delivery';CURRENT=ROOT/'workspace/dino-4r-connector-20261106'
import connector_report as full
read=full.read;save=full.save;esc=full.esc;table=full.table

def main():
    assert read(CURRENT/'verification.json')['acceptance_passed']
    report=OUT/'report';shutil.copytree(CURRENT/'report',report,dirs_exist_ok=True)
    for f in CURRENT.glob('*.json'):shutil.copy2(f,OUT/f.name)
    for name in ('diagnostic-v1','diagnostic-v2'):
        (OUT/name).mkdir(exist_ok=True)
        for f in (CURRENT/name).glob('*.json'):shutil.copy2(f,OUT/name/f.name)
    for f in (CURRENT/'runs').glob('*/result.json'):
        dest=OUT/'runs'/f.parent.name/'result.json';dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,dest)
    cases=read(OUT/'cases.json');rows=read(OUT/'rows.json');plan=read(OUT/'plan.json');summary=read(OUT/'summary.json')
    baseline={r['key']:r for r in rows};trial_rows=[];trial_details=[]
    arms=[('normal_add1','只補正常接點'),('positive_clean3','整理S05／S07／S20'),('clean3_normal_add1','整理三張＋正常接點'),('clean3_normal_add2','再補良品邊界範例')]
    for arm,label in arms:
        completed=[]
        for f in (EXP/'replay').glob(f'*/{arm}.json'):
            r=read(f);b=baseline[r['key']];completed.append((r,b))
            old=read(CURRENT/'runs'/r['key']/'result.json');oldpred={str(c['id']):c['classification'] for c in old['candidates']+old['filtered_candidates']}
            newalarms=[k for k,p in r['predictions'].items() if p['filter_recommendation']=='keep' and oldpred[k]['filter_recommendation']!='keep']
            lost=sorted(set(b['hits'])-set(r['hits']))
            if newalarms or lost or (b['label']=='NG' and r['unmatched']>b['unmatched']):
                trial_details.append(dict(arm=arm,photo=r['key'],new_alarms=newalarms,lost_using_prior_match=lost,NG_unmatched=r['unmatched'] if b['label']=='NG' else None,prior_NG_unmatched=b['unmatched'] if b['label']=='NG' else None))
        ng=sum(b['label']=='NG' for _,b in completed);ok=sum(b['label']=='OK' and not b['is_reference'] for _,b in completed);selfcount=sum(b['is_reference'] for _,b in completed)
        trial_rows.append([label,f'{ng}/10',f'{ok}/89',f'{selfcount}/1','未採用'])
    proof=read(EXP/'stability-clean3_normal_add1.json');minimal=read(EXP/'stability-clean2_normal_add1.json');failed=[dict(id=t['id'],scale=t['scale'],verdict=t['verdict']) for t in minimal['image_resample_tests'] if t['verdict']!='exclude']
    experiment=dict(adopted=False,current_version_unchanged=True,current_answer_hits=summary['answer_hits'],current_NG_unmatched=summary['NG_unmatched'],current_good_alarms=summary['good_alarms'],trial_completion=trial_rows,trial_failures=trial_details,minimal2_image_failures=failed,new_bank_full100_validation_completed=False,reason='Bank changes repair the reported pair but cause new unannotated alarms, or fail image scale stability. Stop expansion of failed trials; retain prior verified policy.')
    save(EXP/'audit-conclusion.json',experiment)
    for p in report.glob('*.html'):
        s=p.read_text(encoding='utf8').replace('</nav>','<a href="bank-audit.html">本輪：DINO範例審查</a></nav>',1)
        if p.name=='index.html':
            s=re.sub(r'<h1>.*?</h1>','<h1>4r｜DINO範例審查與目前100張完整結果</h1>',s,count=1)
            notice='<p class="warn"><strong>本輪只換範例庫的候選方案尚未通過保護條件，未採用。</strong>以下是目前保留的4r完整100張結果：原79處、NG框外34、良品警報2均維持。不是新範例庫的100張驗收。<a href="bank-audit.html">查看本輪證據與失敗方案</a>。</p>'
            s=s.replace('</h1>','</h1>'+notice,1)
        p.write_text(s,encoding='utf8')
    nav='<nav><a href="index.html">目前保留版本：100張完整結果</a><a href="photo-ng-128.html">128全部候選</a></nav>'
    body='<p><strong>結論：固定待測裁圖後，只整理DINO螺絲範例，#40就會由像螺絲轉為正常。範例背景干擾有直接證據，前輪把原因主要歸於取圖並不充分。</strong></p><p>但目前範例庫候選仍出現新警報或縮放翻判，未採用。正式流程、原始模型、來源圖資與既有人工紀錄不變；前輪79處及兩個使用者確認螺絲維持原結果。</p>'
    fixed={r['id']:r for r in read(EXP/'fixed-query-scores.json') if r['photo']=='128' and r['id'] in (22,40)}
    body+='<h2>真正只換範例的對照</h2><p>下面每一列都使用完全相同的原始待測模型輸入與特徵雜湊，仍採原top-3相似度差、零門檻與參照／待測雙圖規則。沒有改待測裁圖、加長寬比條件，或用上一輪接點複核來讓結果一致。分數不是機率。</p>'
    body+=table(['案例','原47＋65','只補正常接點','只整理三張正例','整理三張＋正常接點'],[[f'128 #{cid}']+[f'{fixed[cid]["arms"][a]["target"]["margin"]:+.4f}' for a in ('original','normal_add1','positive_clean3','clean3_normal_add1')] for cid in (40,22)])
    body+='<p>只補一張正常接點不足以修正#40；整理正例的背景才是本例的重要改變。N66只取使用者確認的#22，未把#40加入範例庫。這些案例已在開發時看過，不是盲測。</p>'
    shutil.copy2(EXP/'positive-review-controls.png',report/'positive-review-controls.png')
    body+='<h2>三張螺絲範例的問題</h2><p>S05、S07、S20仍保留螺絲正例標籤。中欄縮小範例中周圍板件／接點背景，保留可見螺絲；這是整理參考範例，不是改待測圖。右欄只作合成診斷：把螺絲所在矩形塗白、保留原背景，沒有放入任何訓練或範例庫。</p><img src="positive-review-controls.png" alt="左原範例，中螺絲範例整理，右背景合成對照">'
    controls=read(EXP/'background-controls.json');lookup={(r['positive'],r['variant']):r for r in controls if r['candidate']==40}
    body+=table(['#40對照的正例','原範例整體相似度','整理後','只留背景（合成）'],[[f'S{n:02}']+[f'{lookup[n,v]["whole"]:.4f}' for v in ('original','object','background')] for n in (5,7,20)])
    body+='<p>三張的背景合成對照，整體相似度都高於原範例；整理後螺絲本身的相似度則明顯降低。這支持模型把正常接點與正例背景混淆；合成對照仍不能單獨代表實際拍攝驗收。</p>'
    inventory=read(EXP/'normal-inventory.json');body+='<h2>65張正常範例的涵蓋範圍</h2><p>以下是助理逐張外觀分類，並非使用者新增人工分類。未見專門涵蓋#22／#40這類長條密集接點的正常例；有一般元件與板邊，不代表正常類完全空白。</p>'+table(['外觀','張數'],list(inventory['counts'].items()))
    body+='<details><summary>展開全部65張正常範例來源圖</summary><div style="display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px">'
    for row in inventory['rows']:
        name=f'normal-N{row["index"]:02}.png'
        with Image.open(row['path']) as im:im.save(report/name)
        body+=f'<article><p>N{row["index"]:02}／{esc(row["category"])}</p><img style="width:160px;height:160px;object-fit:contain;image-rendering:pixelated" src="{name}" alt="正常範例來源圖"></article>'
    body+='</div></details><h2>為何這輪不採用新庫</h2><p>整理三張正例，能修正128 #40，但131仍多留一個接點；再補正常接點可處理131，卻新增132 #137的未對答案警報。加入既有良品參照中的邊界例後，132單步分數下降，但128完整流程新增#23警報。這些不能用總數下降來掩蓋。</p>'
    body+='<p>另測較小修改：只整理S07、S20並補正常接點。原圖判對且固定裁圖測試未少掉原始單步命中，但影像縮放仍失敗，不能稱穩定解決。S05不是錯標螺絲；整理它後更接近某些正常圓形結構，顯示正例與相似正常例需要成組核對。</p>'
    body+=table(['較小修改的失敗案例','影像倍率','實際結果'],[[f'128 #{r["id"]}',r['scale'],'保留警報'] for r in failed])
    body+='<h2>穩定性與實際測試範圍</h2>'+table(['方案','框擾動：排除且同物件','影像縮放：排除'],[['整理三張＋正常接點',f'{sum(t["verdict"]=="exclude" and t["same_object"] for t in proof["query_tests"])}/90',f'{sum(t["verdict"]=="exclude" for t in proof["image_resample_tests"])}/10'],['只整理兩張＋正常接點',f'{sum(t["verdict"]=="exclude" and t["same_object"] for t in minimal["query_tests"])}/90',f'{sum(t["verdict"]=="exclude" for t in minimal["image_resample_tests"])}/10']])
    body+='<p>框位移±4像素，大小75／90／100／110／125%，每次重新分類；影像縮放使用同五倍率與同比例既有候選，沒有重跑候選產生。完整分類回放沿用對位與候選，原有條件分支仍正常執行；原版回放已完成的照片皆核對了判斷、模型輸入與分數，不是套舊結果。</p>'+table(['完整流程對照方案','不良圖完成','一般良品完成','自比完成','狀態'],trial_rows)
    body+='<p>已出現新增警報／縮放失敗的方案未繼續擴大驗收；不把部分回歸稱為新庫100張驗收。首頁仍完整交付目前保留版本的100張、8335候選。前輪已保護的79處、NG框外34及良品2警報皆維持。深色喇叭與小圓頭漏抓仍暫緩；本次檢查邊界只是處理換庫新增的警報。</p>'
    body+='<h2>後續範例整理的依據</h2><p>應成組整理「螺絲本體、相似正常結構、相同背景的有螺絲／無螺絲對照」，維持正常結構的代表性，並先看是否新增錯誤，再看命中總數。不能只把螺絲例裁得更乾淨，也不能只補一個失敗位置當正常例就宣布有效。需以未參與範例整理的照片驗收；目前使用者確認沒有另一批有答案新圖。</p>'
    body+='<p><a href="../../fixed-query-scores.json">同輸入換庫完整分數</a> · <a href="../../background-controls.json">背景合成對照</a> · <a href="../../example-review.json">範例來源與整理範圍</a> · <a href="../../normal67-provenance.json">良品邊界例來源</a> · <a href="../../audit-conclusion.json">本輪結論與測試覆蓋</a> · <a href="../../experiment-plan.json">實驗條件與雜湊</a></p>'
    (report/'bank-audit.html').write_text('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DINO範例審查</title><style>'+full.common.STYLE+'</style><main>'+nav+'<h1>固定待測取圖，審查DINO範例</h1>'+body+'</main></html>',encoding='utf8')
    summary['bank_experiment_adopted']=False;summary['bank_experiment_full100_validated']=False;summary['classification_retained_from']=str(CURRENT);save(OUT/'summary.json',summary)
    assert all((OUT/'runs'/r['key']/'result.json').read_bytes()==(CURRENT/'runs'/r['key']/'result.json').read_bytes() for r in rows)
    full.OUT=OUT;full.verify(report,report/'images',cases,rows,plan,summary)
    v=read(OUT/'verification.json');v.update(bank_experiment_adopted=False,retained_classification_all100_identical=True);save(OUT/'verification.json',v)
    print('AUDIT REPORT READY; experimental banks rejected; current all100 unchanged',flush=True)
if __name__=='__main__':main()
