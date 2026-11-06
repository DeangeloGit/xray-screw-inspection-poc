"""Withdraw unsupported semantic acceptance; preserve historical measurements."""
import json,sys,shutil,os
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import unquote
from PIL import Image
import answered_batch_report as full
ROOT=Path(__file__).resolve().parents[2];EXP=ROOT/'workspace/dino-4r-screw-evidence-20261106';OUT=EXP/'final';BASE=ROOT/'workspace/dino-4r-blackblock-20261106/final';OLD=ROOT/'workspace/dino-4r-hardnegative-20261106/manual-normal/final'
read=full.read;save=full.save
def main():
    reuse='--reuse-full' in sys.argv
    OUT.mkdir(exist_ok=True)
    for name in ('plan.json','answers.json','provenance.json','run-complete.json'):shutil.copy2(BASE/name,OUT/name)
    if not (OUT/'runs').exists():shutil.copytree(BASE/'runs',OUT/'runs')
    meta=read(BASE/'report-meta.json');meta.update(title='4r 螺絲部位證據審查｜全圖資基準',policy_description='沿用59／101基準判斷；前輪黑塊補救尚未證明辨認到螺絲本身，撤回採用結論。正式流程未改。',methods=dict(r3='原r3（同校正答案）',recovery='前輪可交付基準',pilot='目前基準：螺絲證據待釐清'),comparison_description='本輪僅撤回未證實的改善認定，沿用既有推論，不宣稱新增檢出或重跑模型。歷史69／101原始量測保留於附頁追溯。')
    save(OUT/'report-meta.json',meta);save(OUT/'manual-feedback.json',{'128-10':dict(label='screw',text='使用者確認新增／掉落物件。'),'135-88':dict(label='screw',text='使用者確認有掉落螺絲。'),'128-3':dict(label='normal',text='使用者確認正常結構變化，應排除。')})
    if reuse:
        v=read(OUT/'verification.json');assert v['status']=='passed'
        assert all(full.sha(OUT/p)==h for p,h in v['result_sha256'].items())
    else:
        sys.argv=[sys.argv[0],str(OUT)];full.main()
    report=OUT/'report';images=report/'images'
    assert read(OUT/'summary.json')['totals']['pilot']==dict(kept=118,answer_hits=59,unmatched=50)
    for p in (OUT/'runs/pilot').glob('*/result.json'):assert full.sha(p)==full.sha(BASE/'runs/pilot'/p.parent.name/'result.json')
    challenge=read(EXP/'synthetic-challenge.json');assert len(challenge['rows'])==9
    for file in ('128-5-parts.png','original-context.png','block-interior.png'):shutil.copy2(EXP/file,images/file)
    oldlink=os.path.relpath(OLD/'report/index.html',report).replace('\\','/')
    body='<p class="warn">前輪69／101改善成功／採用結論已撤回。該數字仍是歷史量測，但未證明判斷依據是被遮擋螺絲，而非黑塊與周圍背景。不能當成已達成使用者需求。</p><p>目前沿用原59／101、框外警報50基準；原55處及兩處使用者確認螺絲保住。這是交付基準修正，不是新演算法改善；正式流程、原圖、原始答案、歷史推論未改。</p>'
    body+='<h2>要辨認的是螺絲本身</h2><p>只有黑塊應排除；有被遮擋螺絲時，必須指出能支持螺絲的部位或影像特徵。前輪把整張黑塊裁圖加入螺絲例，未做同樣黑塊有／無螺絲的成對驗證，且框位移測試只能證明判斷一致，不能證明判斷依據正確。</p>'
    body+='<h2>128-5 部位待確認</h2><p>A為頂端突出、B為右側半圓、C為黑塊內部。D為另一個清楚工字形物件，已由候選128-87命中答案7，不能拿D證明128-5命中了答案10。已詢問使用者真正的被遮擋螺絲部位，目前不自行標註A／B／C為螺絲。</p><img src="images/128-5-parts.png"><p><a href="photo-128.html#case-128-5">完整照片與128-5候選</a> · <a href="photo-128.html#case-128-87">已命中的128-87</a></p>'
    body+='<details><summary>原始參照／待測脈絡與黑塊內部對比</summary><img src="images/original-context.png"><img src="images/block-interior.png"><p>對比拉伸只是檢視方法，不能把雜訊或紋理當作確定螺絲。</p></details>'
    body+='<h2>九個只有深色矩形的合成挑戰</h2><p>從參照圖加入均勻深色矩形，不使用待測圖的螺絲像素。九個都未通過前輪補救條件。這不證明前輪辨認到了螺絲，也不是實拍驗收；合成挑戰只供診斷。</p>'+full.table(['照片','矩形亮度','參照分數','待測分數','前輪補救是否放行'],[[r['photo'],r['value'],round(r['pair']['reference']['margin'],4),round(r['pair']['target']['margin'],4),r['rescue_gate']] for r in challenge['rows']])
    body+=f'<p><a href="{oldlink}">歷史69／101完整實驗報告（採用結論已撤回）</a> · <a href="../../synthetic-challenge.json">合成挑戰原始結果</a></p>'
    (report/'screw-evidence.html').write_text('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>螺絲部位證據審查</title><style>'+full.STYLE+'</style><main>'+full.NAV+'<h1>螺絲部位證據審查</h1>'+body+'</main></html>',encoding='utf-8')
    for p in report.glob('*.html'):
        text=p.read_text(encoding='utf-8')
        if 'href="screw-evidence.html"' not in text:text=text.replace('</nav>','<a href="screw-evidence.html">附加：螺絲部位證據審查</a></nav>',1)
        p.write_text(text,encoding='utf-8')
    newlink=os.path.relpath(report/'index.html',OLD/'report').replace('\\','/')
    banner=f'<aside id="semantic-acceptance-withdrawn" style="background:#fff0d5;border:2px solid #ba6500;padding:18px;margin:20px"><strong>歷史實驗：改善成功／採用結論已撤回。</strong> 尚未證明模型辨認到被遮擋螺絲；69／101保留為歷史量測，不視為需求驗收通過。<a href="{newlink}">查看目前全圖資基準及審查</a>。</aside>'
    for p in (OLD/'report').glob('*.html'):
        text=p.read_text(encoding='utf-8')
        if 'id="semantic-acceptance-withdrawn"' not in text:text=text.replace('</nav>','</nav>'+banner,1)
        p.write_text(text,encoding='utf-8')
    save(OLD/'semantic-acceptance-review.json',dict(accepted=False,reason='No evidence that rescue recognizes the occluded screw itself; whole black-block crops used as positive examples.',historical_measurements_preserved=True,current_baseline=str(OUT),user_requirement='有被遮擋的掉落螺絲才判螺絲；只有黑塊不能判螺絲'))
    class Parser(HTMLParser):
        def __init__(self):super().__init__();self.ids=[];self.links=[]
        def handle_starttag(self,t,a):
            d=dict(a)
            if 'id' in d:self.ids.append(d['id'])
            self.links.extend(d[k] for k in ('src','href') if k in d)
    count=0;oldcount=0;parsed={}
    def parse(p):
        p=p.resolve()
        if p not in parsed:
            v=Parser();v.feed(p.read_text(encoding='utf-8'));assert len(v.ids)==len(set(v.ids));parsed[p]=v
        return parsed[p]
    for directory in (report,OLD/'report'):
        for p in directory.glob('*.html'):
            parser=parse(p)
            for link in parser.links:
                name,_,anchor=link.partition('#');dest=(p.parent/unquote(name)).resolve() if name else p.resolve();assert dest.exists(),(p,link)
                if anchor:
                    assert anchor in parse(dest).ids,(p,link)
                if directory==report:count+=1
                else:oldcount+=1
    fs=[p for p in images.iterdir() if p.suffix in ('.jpg','.png')]
    for p in fs:
        with Image.open(p) as im:im.verify()
    v=read(OUT/'verification.json');v.update(html_pages=len(list(report.glob('*.html'))),links_checked=count,images_checked=len(fs),historical_report_links_rechecked=oldcount,selected_inference_identical_to_baseline=True,semantic_rescue_not_accepted=True);save(OUT/'verification.json',v)
    print('CURRENT BASELINE FULL REPORT VERIFIED',v['html_pages'],count,len(fs),'historical links',oldcount)
if __name__=='__main__':main()
