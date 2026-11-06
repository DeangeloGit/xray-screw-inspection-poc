"""Deliver the actual reference collection with the intact full-corpus report."""
from reference_set_prepare import ROOT,OUT as EXP,PRIOR,read,save
import hashlib,shutil,zipfile,html,re
from pathlib import Path
from PIL import Image,ImageDraw
import connector_report as full

def main():
    OUT=EXP/'delivery';report=OUT/'report';current=ROOT/'workspace/dino-4r-connector-20261106';collection=EXP/'collection';manifest=read(collection/'manifest.json');scores=read(EXP/'fixed-query-summary.json');details=read(EXP/'fixed-query-scores.json')
    shutil.copytree(current/'report',report,dirs_exist_ok=True)
    for f in current.glob('*.json'):shutil.copy2(f,OUT/f.name)
    for name in ('diagnostic-v1','diagnostic-v2'):
        (OUT/name).mkdir(exist_ok=True)
        for f in (current/name).glob('*.json'):shutil.copy2(f,OUT/name/f.name)
    for f in (current/'runs').glob('*/result.json'):
        dest=OUT/'runs'/f.parent.name/'result.json';dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,dest)
    esc=html.escape;table=full.table
    css=full.common.STYLE+' .samples{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.sample img{width:180px;height:180px;object-fit:contain;image-rendering:pixelated}.sample{padding:12px;border:1px solid #ccd}.sample small{display:block}.sample span{display:inline-flex;flex-direction:column;vertical-align:top;margin:4px} @media(max-width:700px){.samples{grid-template-columns:1fr}}'
    def sample(z):
        imgs=''
        for mode in ('core','context'):
            filename=f'refset-{z["id"]}-{mode}.png';shutil.copy2(z['views'][mode]['file'],report/filename)
            imgs+=f'<span>{"本體" if mode=="core" else "少量背景"}<img src="{filename}" alt="{esc(z["id"])} {mode}"></span>'
        return f'<article class="sample"><h3>{z["id"]}｜{esc(z["family"])}</h3>{imgs}<small>來源：{"Golden" if z["side"]=="reference" else "不良圖128"}，範圍 {z["box"]}。{ "使用者確認" if "user" in z["authority"] else "既有答案＋助理外觀整理" if z["label"]=="screw" else "助理外觀審查；非新增人工標籤"}</small></article>'
    body='<p><strong>已建好可追溯的候選參考集，尚未替換目前4r檢測庫。</strong>這套依目標X光影像重新挑選，不受原47＋65張限制。每個物件有來源座標、影像雜湊及本體／少量背景兩種版本；同一物件的縮放、旋轉不算新案例。</p>'
    body+=table(['用途','數量','怎麼使用'],[['完整螺絲正例',8,'頭桿、圓頭、板上重疊、線材旁、明暗邊界'],['正常背景與結構',27,'8個同位置Golden＋18個Golden正常結構＋使用者確認的#22'],['B局部配對',2,'1正例＋1同位置Golden；不混入完整物件主庫'],['歧義／黑塊本體控制',16,'固定圓頭、孔環、混合正常結構；不強制標不像螺絲'],['保留檢查',2,'#40密集接點、#3正常黑塊；不加入範例']])
    body+='<h2>需要哪些參考內容</h2><p>螺絲例要看得到頭、桿或已確認的外露部分；正常例要涵蓋長條密集接點、板上焊點／元件、線材、板邊及U形結構。每一種螺絲背景都要有同位置無掉落物件的Golden對照。不能把整塊黑影當螺絲，也不能因Golden是良品，就把其中固定圓頭教成「不像螺絲」。固定螺絲外觀仍可能像螺絲，是否新增要交給雙圖判斷。</p>'
    body+='<p>已把5個原先擬作正常例、但實際視野含固定圓頭的項目移出主庫。正常例分類由助理審查，未寫回使用者人工紀錄。深色喇叭與難辨小圓頭共22處沿用暫緩範圍。</p>'
    body+='<h2>來源與答案對位</h2><p>只用128有答案圖與其Golden建庫。101處既有答案經旋轉、縮放、配準及局部對位換算，回原圖誤差最大小於0.15像素；答案座標沒有移動來配合預測。其餘9張的70處非暫緩答案保留作開發檢查，89張一般良品未提供本輪新範例。這些仍是先前看過的同批圖，並非新批盲測。</p>'
    for side,name in [('reference','Golden'),('aligned','128')]:
        im=Image.open(PRIOR/'runs/ng-128'/f'{side}.png').convert('RGB');d=ImageDraw.Draw(im)
        for z in manifest['examples']:
            if z['side']!=('reference' if side=='reference' else 'target'):continue
            x,y,w,h=z['box'];color='#00a0ff' if z['label']=='screw' else '#e06020' if z['role']=='main_reference' else '#a000a0';d.rectangle((x,y,x+w,y+h),outline=color,width=2);d.text((x,y-12),z['id'],fill=color)
        im.save(report/f'refset-overview-{side}.png')
    body+='<details><summary>展開全圖來源與選例位置（左Golden／右待測128）</summary><div class="samples"><img src="refset-overview-reference.png" alt="Golden選例位置"><img src="refset-overview-aligned.png" alt="128選例位置"></div></details>'
    lookup={r['id']:r for r in manifest['examples']}
    body+='<h2>完整螺絲與相同位置背景</h2><p>左：Golden無新增螺絲；右：答案螺絲。兩種範圍是替代版本，不能灌成兩個獨立物件。</p><div class="samples">'
    for z in manifest['examples']:
        if z['role']=='main_reference' and z['label']=='screw':body+=sample(lookup[z['paired_example']])+sample(z)
    body+='</div><h2>容易混淆的正常結構</h2><div class="samples">'
    for z in manifest['examples']:
        if z['role']=='main_reference' and z['label']=='non_screw' and not z['paired_example']:body+=sample(z)
    body+='</div><h2>B只辨認外露螺絲部分</h2><p>左同位置Golden、右B。白色只是補成正方形，沒有生成或補畫螺絲；兩例獨立保留，未直接套用主庫top-3規則。</p><div class="samples">'+sample(lookup['G10'])+sample(lookup['P10'])+'</div>'
    body+='<h2>歧義控制與保留檢查（不進訓練庫）</h2><details><summary>展開18個控制案例</summary><div class="samples">'
    for z in manifest['examples']:
        if z['role'] in ('pair_control_only','heldout_normal'):body+=sample(z)
    body+='</div></details><h2>固定待測輸入，只換參考庫</h2><p>以下1345個不良圖候選重算相似度，全部沿用相同的待測／參照特徵與原top-3、零門檻規則。沒有改待測取圖，也沒有接點額外排除規則。這是單步診斷，仍核對全部既有答案，暫緩項目未刪標籤；不能把此處命中數當完整流程的79處。</p>'
    names={'original':'原47＋65','new_core':'全新本體庫8＋27','new_context':'全新少量背景庫8＋27','old_plus_core':'原庫＋新本體','old_plus_context':'原庫＋新少量背景'}
    body+=table(['組別','範例方案','單步命中','遺失原單步命中','未對答案候選','新增未對答案候選'],[[('建庫圖128' if s['split']=='construction_128' else '其餘9張'),names[s['arm']],s['raw_hits'],len(s['lost_vs_same_stage']),s['unmatched'],len(s['new_unmatched'])] for s in scores])
    pair=[r for r in details if r['photo']=='128' and r['id'] in (22,40)]
    body+=table(['待測分數（非機率）']+list(names.values()),[[f'128 #{r["id"]}']+[f'{r["arms"][a]["target"]["margin"]:+.4f}' for a in names] for r in pair])
    body+='<p><strong>候選庫仍不可直接採用。</strong>新參考內容是否適合，必須同時看其他螺絲與新增警報，不能只看#40。此次未完成新庫完整流程100張驗收或新庫框位移／縮放驗收，未宣稱保住79處。首頁保留已驗證4r完整100張：79／101、NG未對答案34、一般良品2、自比0；全部分類檔逐位元核對相同。</p>'
    body+='<p>目前最適合作為後續整理基礎的是這套「可見螺絲＋同位置背景＋相似正常結構＋歧義控制」分工，不是把所有案例混成一個正負資料夾。單張建庫仍缺不同拍攝條件與獨立螺絲姿態；8個主正例不足以證明可取代原47張。保留原庫與新庫的對照實驗，不宣布已找到全域最佳庫。</p>'
    body+='<p><a href="../../collection/manifest.json">來源／標籤／範圍清單</a> · <a href="../../fixed-query-scores.json">全部逐候選分數</a> · <a href="../../evaluation-scope.json">實際測試範圍</a> · <a href="../../reference-collection.zip">下載參考案例集</a></p>'
    nav='<nav><a href="index.html">100張全圖資結果</a><a href="photo-ng-128.html">128完整候選</a></nav>'
    page='<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>4r新參考案例集</title><style>'+css+'</style><main>'+nav+'<h1>4r｜由答案圖與Golden建立的參考案例集</h1>'+body+'</main></html>'
    (report/'reference-collection.html').write_text(page,encoding='utf8')
    for p in report.glob('*.html'):
        if p.name=='reference-collection.html':continue
        s=p.read_text(encoding='utf8').replace('</nav>','<a href="reference-collection.html">新參考案例集</a></nav>',1)
        if p.name=='index.html':s=s.replace('</h1>','</h1><p class="warn">本輪已建立新參考候選集，尚未替換檢測庫。下方是維持不變的100張完整結果；<a href="reference-collection.html">新庫圖片、來源與固定輸入比較在附頁</a>，不是新庫100張驗收。</p>',1)
        p.write_text(s,encoding='utf8')
    portable=read(collection/'manifest.json')
    for z in portable['examples']:
        for v in z['views'].values():v['file']='images/'+Path(v['file']).name
    save(collection/'portable-manifest.json',portable)
    save(collection/'evaluation-summary.json',dict(summary=scores,scope=read(EXP/'evaluation-scope.json')))
    (collection/'README.txt').write_text('4r 參考案例候選集\n\n8完整螺絲＋27正常例為主庫；1個B部位＋1同位置背景獨立保存。16個歧義控制及2個保留檢查不進主庫。\ncore/context為替代範圍，旋轉與縮放不算獨立物件。NPZ只包含35個主庫物件，每物件8個方向。\nportable-manifest.json中的檔案路徑相對本資料夾，來源及座標可追溯。\n新庫尚未通過完整100張／79處保護驗收，不可直接取代正式模型。evaluation-summary.json記錄固定待測特徵的比較。\n',encoding='utf8')
    with zipfile.ZipFile(EXP/'reference-collection.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in collection.rglob('*'):
            if p.is_file():z.write(p,p.relative_to(collection))
    checksum=hashlib.sha256((EXP/'reference-collection.zip').read_bytes()).hexdigest();(EXP/'reference-collection.zip.sha256').write_text(checksum+'  reference-collection.zip\n',encoding='ascii')
    cases=read(OUT/'cases.json');rows=read(OUT/'rows.json');plan=read(OUT/'plan.json');summary=read(OUT/'summary.json')
    assert all((OUT/'runs'/r['key']/'result.json').read_bytes()==(current/'runs'/r['key']/'result.json').read_bytes() for r in rows)
    summary.update(new_reference_collection_adopted=False,new_bank_full100_validated=False,retained_classification_all100_identical=True);save(OUT/'summary.json',summary)
    full.OUT=OUT;full.verify(report,report/'images',cases,rows,plan,summary)
    check=read(OUT/'verification.json');check.update(new_reference_collection_adopted=False,new_bank_full100_validated=False,retained_classification_all100_identical=True);save(OUT/'verification.json',check)
    for z in portable['examples']:
        for v in z['views'].values():assert hashlib.sha256((collection/v['file']).read_bytes()).hexdigest()==v['sha256']
    with zipfile.ZipFile(EXP/'reference-collection.zip') as z:assert z.testzip() is None
    save(EXP/'collection-verification.json',dict(status='passed',unique_records=len(portable['examples']),main_examples=35,image_views=110,zip_sha256=checksum,all_sources=sorted(set(z['raw_source'] for z in portable['examples'])),raw_source_sha256={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in set(z['raw_source'] for z in portable['examples'])},classification_adopted=False))
    print('REFERENCE COLLECTION AND FULL REPORT READY',flush=True)
if __name__=='__main__':main()
