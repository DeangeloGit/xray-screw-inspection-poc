"""Full corpus delivery; unsafe factorial variants remain comparison evidence."""
import copy,hashlib,json,shutil,sys,re,html
import numpy as np
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import unquote
from PIL import Image,ImageDraw
import answered_batch_report as full
ROOT=Path(__file__).resolve().parents[2];EXP=ROOT/'workspace/dino-4r-blackblock-20261106';BASE=ROOT/'workspace/dino-4r-correspondence-20261106/final';OUT=EXP/'final'
read=full.read;save=full.save
NAMES={'original_old':'原取圖＋原範例','square_old':'只改完整方形取圖','original_new':'只補3個範例','square_new':'取圖與範例都改'}
def main():
    OUT.mkdir(exist_ok=True);plan=read(BASE/'plan.json');evaluation=read(EXP/'factorial-evaluation.json')
    assert all(not evaluation['variants'][k]['rescue_only']['passes_safety'] for k in ('square_old','original_new','square_new'))
    for name in ('provenance.json',):shutil.copy2(BASE/name,OUT/name)
    answers=read(EXP/'answers-corrected.json');save(OUT/'answers.json',answers)
    review=OUT/'reviewed-answer-images';review.mkdir(exist_ok=True)
    for row in plan['items']:
        if row['key']=='golden':continue
        im=Image.open(row['path']).convert('RGB');d=ImageDraw.Draw(im)
        for m in answers[row['key']]['marks']:
            pts=[tuple(p) for p in m['polygon']];d.line(pts+[pts[0]],fill='red',width=5);d.text(tuple(m['center']),str(m['id']),fill='red',stroke_width=2)
        path=review/f'{row["key"]}.png';im.save(path);row['original_answer']=row['answer'];row['answer']=str(path)
    save(OUT/'plan.json',plan)
    for dest,source in [('r3','r3'),('recovery','pilot'),('pilot','pilot')]:
        if not (OUT/'runs'/dest).exists():
            if dest=='pilot':shutil.copytree(BASE/'runs'/source,OUT/'runs'/dest)
            else:
                for folder in (BASE/'runs'/source).iterdir():
                    target=OUT/'runs'/dest/folder.name;target.mkdir(parents=True,exist_ok=True)
                    for name in ('result.json','complete.json'):shutil.copy2(folder/name,target/name)
    save(OUT/'run-complete.json',dict(complete=True,selected_detection='unchanged baseline',inference_results_reused_for_report_only=True))
    save(OUT/'report-meta.json',dict(title='4r 校正評分與大黑塊驗證｜全圖資結果',methods=dict(r3='原 r3（同校正答案）',recovery='前輪安全版（校正評分）',pilot='本輪交付：沿用安全版'),expected_answers=101,reviewed_scoring=True,protect_r3_candidates=False,protect_previous_answer_hits=True,protect_unmatched=True,policy_description='本輪實驗會增加誤報，未採用；實際交付判斷與前輪相同。校正評分與演算法提升分開列出。',comparison_description='本頁三版本均採相同校正答案。四組取圖／範例試驗另見實驗附頁；不將校正評分當成模型新增命中。',answer_intro='<p>原100處答案保留不動，另存4處定位校正（133答案3、135答案1、137答案6、130答案10），並加入使用者確認的128候選10為答案11，共101處。135線材螺絲原已在100處內，不重複加計。下列圖為獨立校正覆蓋圖，原始PNG及逐筆前後座標可追溯。匹配仍用原中心／重疊規則，不為個別版本放寬。</p>'))
    sys.argv=[sys.argv[0],str(OUT)];full.main();report=OUT/'report';images=report/'images'
    results=read(EXP/'ablation-results.json');idx={f'{z["photo"]}-{z["id"]}':z for z in results}
    cases=read(OUT/'cases.json');ci={c['key']:c for c in cases};allmarks=read(OUT/'answer-matches.json');baseline=read(EXP/'corrected-baseline.json')
    assert read(OUT/'summary.json')['totals']['pilot']==dict(kept=118,answer_hits=59,unmatched=50)
    before=read(BASE/'summary.json');current=read(OUT/'summary.json')
    original55={(m['photo'],m['id']) for m in read(BASE/'answer-matches.json') if m['methods']['pilot']};after={(m['photo'],m['id']) for m in allmarks if m['methods']['pilot']}
    assert original55<=after and {('128',11),('135',1)}<=after
    for f in (OUT/'runs/pilot').glob('*/result.json'):assert full.sha(f)==full.sha(BASE/'runs/pilot'/f.parent.name/'result.json')
    corrections=read(EXP/'scoring-corrections.json');body='<p>首頁為全圖資安全版本；本頁為校正與實驗附加證據。所有1,345候選都有四組對照，可從照片或類型頁逐一展開。正式流程、模型、原始答案不變。</p>'
    body+='<h2>先把評分算對</h2>'+full.table(['口徑','命中','答案框外警報','說明'],[['原100處原規則','55／100',55,'前輪原始值保留'],['校正後同一份輸出','59／101',50,'沒有重跑或增加任何檢出；4處定位校正＋1處新增人工答案'],['本輪交付','59／101',50,'實驗未通過誤報限制，沿用安全判斷']])
    body+='<p>59來自原55、133答案3／135答案1／137答案6三處原已有警報的修正，以及128新增人工答案1處。130答案10定位修正後仍未命中，不增加分數。兩處使用者確認螺絲均保住，135答案1只計一次。</p>'
    for z in corrections:
        key=z['photo'];mid=z['answer_id'];shutil.copy2(next(i['answer'] for i in read(BASE/'plan.json')['items'] if i['key']==key),images/f'original-answer-{key}.png')
        body+=f'<details><summary>{key}／答案{mid}：'+('新增人工答案' if z['old'] is None else '定位校正')+f'</summary><p><a href="photo-{key}.html">完整照片</a> · <a href="images/original-answer-{key}.png">原始PNG標註</a> · <a href="images/{key}-answer.jpg">校正覆蓋圖</a></p><pre>'+full.esc(json.dumps(dict(old=z['old'],new=z['new']),ensure_ascii=False,indent=2))+'</pre></details>'
    body+='<h2>固定的四組對照</h2><p>只把128、131、132三張的完整大黑塊加入正樣本；驗證為129、130、133～137七張。原47張螺絲與65張正常範例完整保留，試驗銀行為50＋65，僅存實驗目錄。新增範例的取圖固定為原方式，不隨查詢取圖組別改變，因此可分辨取圖與範例的影響。ONNX權重不變。</p><p>取圖對照：原長方形候選外圍12像素，與中心相同的完整方形、邊長=max(w,h)+8。原模型長方形輸入會縮放再中央裁切；方形方案避免較長方向被切掉。</p><p class="warn">這是同一批已用於開發的影像，物件與背景高度相近。只有新增3張範例做到照片分離，不能宣稱外部獨立驗收或保證新機種泛化。沒有一般良品圖。新增範例有助於這組目標的結果，不能直接當成可以上線。</p>'
    body+=full.table(['方案','大黑塊全部10處','開發3處','驗證7處','全批校正答案','框外警報','採用'],[[NAMES[k],f"{e['rescue_only']['all']['big_block_hits']}/10",f"{e['rescue_only']['training']['big_block_hits']}/3",f"{e['rescue_only']['heldout']['big_block_hits']}/7",f"{e['rescue_only']['all']['answer_hits']}/101",e['rescue_only']['all']['unmatched'],'維持原版' if k=='original_old' else '否：誤報增加'] for k,e in evaluation['variants'].items()])
    body+='<p>上表採保守補救路徑：原保留候選維持，只對原本「待測不像螺絲」且沒有結構否決的候選測試新判斷；不繞過參照與結構排除。四組均保住原55處及兩處人工確認，但三個改動方案的框外警報仍增加，故不採用。不是為保住命中而接受更多誤報。</p>'
    body+='<h2>具體結論</h2><p>只改取圖仍未救回任何大黑塊；固定原取圖、只補範例即救回驗證7／7。就此批與這個取圖方案而言，主要問題在原範例／特徵比對對這種外觀支持不足，並非僅靠完整取圖即可解決。新增正樣本同時拉高許多正常黑色結構的分數，所以直接擴充全域範例庫不安全。下一步應在獨立驗證下研究新增物件的參照差異與專用複核條件，不能直接放寬門檻或把所有大黑塊都當螺絲。</p>'
    body+='<h2>三個新增範例</h2>'
    for photo in ('128','131','132'):
        shutil.copy2(EXP/'training-examples'/f'{photo}.png',images/f'training-{photo}.png');body+=f'<article><p>開發照片 {photo}；不含任何驗證照片裁圖</p><img src="images/training-{photo}.png" style="width:224px"></article>'
    body+='<h2>10處大黑塊逐張結果</h2>'
    for photo in map(str,range(128,138)):
        mark=next(m for m in allmarks if m['photo']==photo and m['id']==10);c=next(c for c in cases if c['photo']==photo and 10 in c['answers']);z=idx[c['key']]
        body+=f'<article><h3>{photo}／{c["key"]}：'+('開發' if photo in ('128','131','132') else '驗證')+f'</h3><a href="photo-{photo}.html#case-{c["key"]}">完整照片及同類案例</a><img class="pair" src="images/{c["key"]}.jpg">'+full.table(['方案','參照分數','待測分數','模型雙圖結果'],[[NAMES[k],round(v['reference']['margin'],5),round(v['target']['margin'],5),'保留' if v['keep'] else '排除'] for k,v in z['variants'].items()])+'</article>'
    body+='<h2>新增框外警報：全部列出</h2>'
    for k in ('square_old','original_new','square_new'):
        e=evaluation['variants'][k]['rescue_only'];bad=set(e['all']['unmatched_candidates'])-set(evaluation['baseline']['unmatched_candidates'])
        body+=f'<details><summary>{NAMES[k]}：新增 {len(bad)} 個框外警報</summary>'+''.join(f'<p><a href="photo-{ci[x]["photo"]}.html#case-{x}">{x}</a></p><img class="pair" src="images/{x}.jpg">' for x in sorted(bad))+'</details>'
    body+='<details><summary>直接替換整個DINO判斷的結果（不採用，會損失既有命中）</summary>'+full.table(['方案','命中','框外警報','原55損失'],[[NAMES[k],e['replace_all']['all']['answer_hits'],e['replace_all']['all']['unmatched'],len(e['replace_all']['all']['lost_original55'])] for k,e in evaluation['variants'].items()])+'</details>'
    body+='<p><a href="../../scoring-corrections.json">逐筆校正紀錄</a> · <a href="../../factorial-evaluation.json">四組全部評分</a> · <a href="../../experiment-plan.json">固定切分與條件</a> · <a href="../../ablation-results.json">全部候選分數與輸入雜湊</a></p>'
    (report/'blackblock.html').write_text('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>校正評分與大黑塊驗證</title><style>'+full.STYLE+'</style><main>'+full.NAV+'<h1>校正評分與大黑塊：取圖或範例？</h1>'+body+'</main></html>',encoding='utf-8')
    def add_variants(match):
        key=match.group(1);z=idx[key]
        block='<details><summary>本候選四組模型對照（非交付判斷）</summary>'+full.table(['方案','參照','待測','雙圖'],[[NAMES[k],round(v['reference']['margin'],4),round(v['target']['margin'],4),'保留' if v['keep'] else '排除'] for k,v in z['variants'].items()])+'</details>'
        return match.group(0).replace('</article>',block+'</article>')
    for p in report.glob('*.html'):
        text=p.read_text(encoding='utf-8').replace('</nav>','<a href="blackblock.html">附加：校正評分與大黑塊實驗</a></nav>',1)
        text=re.sub(r'<article id="case-([^"]+)">[\s\S]*?</article>',add_variants,text);p.write_text(text,encoding='utf-8')
    class Parser(HTMLParser):
        def __init__(self):super().__init__();self.ids=[];self.links=[]
        def handle_starttag(self,t,a):
            d=dict(a)
            if 'id' in d:self.ids.append(d['id'])
            self.links.extend(d[k] for k in ('href','src') if k in d)
    parsed={}
    for p in report.glob('*.html'):
        v=Parser();v.feed(p.read_text(encoding='utf-8'));assert len(v.ids)==len(set(v.ids));parsed[p.resolve()]=v
    links=0
    for p,v in parsed.items():
        for link in v.links:
            name,_,anchor=link.partition('#');dest=(p.parent/unquote(name)).resolve() if name else p;assert dest.exists(),(p,link)
            if anchor:assert anchor in parsed[dest].ids,(p,link)
            links+=1
    files=[p for p in images.iterdir() if p.suffix in ('.jpg','.png')]
    for p in files:
        with Image.open(p) as im:im.verify()
    for p,h in read(EXP/'experiment-plan.json')['protected_hashes'].items():assert full.sha(p)==h
    for p,h in read(EXP/'ablation-frozen.json').items():assert full.sha(p)==h
    old=np.load(ROOT/'models/dino-paired-optimized-47-20261104-r3/paired-features.npz')['bank'];new=np.load(EXP/'experimental-bank.npz')['bank']
    assert np.array_equal(new[:47],old[:47]) and np.array_equal(new[50:],old[47:])
    for pattern in ('photo-*.html','category-*.html'):
        assert sum(p.read_text(encoding='utf-8').count('本候選四組模型對照（非交付判斷）') for p in report.glob(pattern))==1345
    verify=read(OUT/'verification.json');verify.update(html_pages=len(parsed),links_checked=links,images_checked=len(files),all_four_variants_all_candidates=True,original55_preserved=True,both_confirmed_preserved=True,selected_results_identical_to_previous=True,prior_stability_preserved_by_byte_identical_results=True,unsafe_variants_not_adopted=True)
    verify.update(original_47_and_65_bank_entries_identical=True,all_photo_and_category_variant_tables_covered=True,frozen_experiment_files_unchanged=True)
    save(OUT/'verification.json',verify);print('FULL REPORT VERIFIED',len(parsed),links,len(files))
if __name__=='__main__':main()
