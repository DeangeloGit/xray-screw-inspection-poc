"""Build an explicit, auditable 4r continuation station; never copy the full corpus."""
import argparse, hashlib, json, shutil, subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
import station_transfer as transfer

ROOT=Path(__file__).resolve().parents[1]
EXP=ROOT/'workspace/dino-4r-integrated-bank-20261106'

def read(p):return json.loads(p.read_text(encoding='utf8'))
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')
class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[]
    def handle_starttag(self,tag,attrs):
        self.links += [v for k,v in attrs if k in ('href','src') and v]

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--destination',type=Path,required=True);ap.add_argument('--resume',action='store_true');a=ap.parse_args();dest=a.destination.resolve()
    if dest.exists() and not (a.resume and dest.is_relative_to(ROOT/'workspace/handoffs') and not (dest/'archives/LEAN-SCOPE.json').exists()):raise ValueError('Use a new destination; only unfinished local staging may resume')
    selected={}
    def add(src,rel,reason):
        src=Path(src).resolve();assert src.is_file(),src
        if rel in selected:assert selected[rel][0]==src;return
        selected[rel]=(src,reason)
    def archive(src,reason):
        src=Path(src).resolve();add(src,'archives/workspace/'+src.relative_to(ROOT/'workspace').as_posix(),reason)
    def tree(src,rel,reason):
        for p in Path(src).rglob('*'):
            if p.is_file():add(p,rel+'/'+p.relative_to(src).as_posix(),reason)
    # The original production contract stays 47+65 and paired; only one model version.
    ver='dino-paired-optimized-47-20261104-r3'
    add(ROOT/'models/active.json','models/active.json','正式DINO模型與112參考圖')
    tree(ROOT/'models'/ver,'models/'+ver,'正式DINO模型與112參考圖')
    # Preserve every page/image and all linked evidence in the latest full report.
    todo=list((EXP/'final/report').glob('*.html'));seen=set()
    while todo:
        p=todo.pop().resolve()
        if p in seen:continue
        seen.add(p);assert p.is_relative_to(EXP),p
        archive(p,'最新完整報告與連結證據')
        if p.suffix=='.html':
            parser=Links();parser.feed(p.read_text(encoding='utf8'))
            for url in parser.links:
                u=urlsplit(url)
                if u.scheme or u.netloc:raise ValueError('Unexpected external report dependency: '+url)
                if u.path:todo.append((p.parent/unquote(u.path)).resolve())
    for name in ('cases.json','rows.json','answers.json','answer-matches.json','visible-part-protection.json','column-verification.json'):
        archive(EXP/'final'/name,'答案與驗證紀錄')
    for name in ('curated_v5_review-recipe.json','bank-build-verification.json','human-unconfirmed-128-7.json','human88-scale-diagnosis.json','reference-role-counterfactuals-v5.json','attribution-summary.json'):
        archive(EXP/name,'答案與驗證紀錄')
    tree(EXP/'active-reference-collection','archives/workspace/'+EXP.name+'/active-reference-collection','實際整合主庫及141參考圖')
    # Bank inputs and all small source examples, including inactive/ambiguous controls.
    for dirname,names in {
        'dino-4r-bank-only-20261106':['original-bank.npz','positive_clean3-bank.npz','example-review.json'],
        'dino-4r-example-audit-20261106':['letterbox-112-bank.npz'],
        'dino-4r-visible-screw-20261106':['visible-part-bank.npz','v3/experiment-plan.json','part-bank-plan.json','training-part-scores.json','user-feedback.json','v2/B-annotation-changes.json'],
        'dino-4r-connector-20261106':['normal-connector-bank.npz','normal-example-22.png','human-confirmations.json'],
        'dino-4r-blackblock-20261106':['scoring-corrections.json'],
        'dino-4r-correspondence-20261106':['annotation-audit.json'],
    }.items():
        for name in names:archive(ROOT/'workspace'/dirname/name,'副庫、參考圖與人工紀錄')
    for dirname,sub in [('dino-4r-visible-screw-20261106','part-examples'),('dino-4r-reference-set-20261106','collection')]:
        tree(ROOT/'workspace'/dirname/sub,'archives/workspace/'+dirname+'/'+sub,'副庫、參考圖與人工紀錄')
    plan=read(EXP/'final/plan.json')
    add(Path(plan['reference']),'workspace/data/Golden.tiff','續作影像：Golden、128、135')
    for key in ('ng-128','ng-135'):
        item=next(i for i in plan['items'] if i['key']==key)
        add(Path(item['path']),'workspace/data/'+key+'.tiff','續作影像：Golden、128、135')
        for name in ('result.json','reference.png','aligned.png'):
            archive(ROOT/'workspace/dino-4r-crossbatch-20261106/runs'/key/name,'兩張續作所需對位影像與候選')
    reasons=Counter();rows=[]
    def copy_one(item):
        rel,(source,reason)=item;target=dest/rel;target.parent.mkdir(parents=True,exist_ok=True)
        digest=transfer.sha(source)
        if not target.exists() or transfer.sha(target)!=digest:shutil.copy2(source,target)
        assert transfer.sha(target)==digest
        return dict(path=rel,source=str(source),bytes=source.stat().st_size,sha256=digest,reason=reason)
    with ThreadPoolExecutor(max_workers=8) as pool:
        for i,row in enumerate(pool.map(copy_one,sorted(selected.items())),1):
            rows.append(row);reasons[row['reason']]+=row['bytes']
            if i%1000==0:print('COPIED',i,'/',len(selected),flush=True)
    for n in ('data','outputs','state','reports','review'):(dest/'workspace'/n).mkdir(parents=True,exist_ok=True)
    write(dest/'config/station.json',dict(schema_version=1,workspace='../workspace',model_root='../models',default_provider='cpu',allow_cpu_fallback=True,acquisition=dict(source='',enabled=False)))
    write(dest/'workspace/state/ui_settings.json',dict(machine_profiles=[dict(id='lean-4r-MPT10',name='MPT10 4r續作研究站',reference=str(dest/'workspace/data/Golden.tiff'),reference_name='Golden.tiff')],selected_machine='lean-4r-MPT10',acquisition=dict(source='',enabled=False),dino_execution='cpu',allow_cpu_fallback=True))
    scope=dict(schema_version=1,scope='lean_4r_continuation_not_full_original_station_backup',source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),source_corpus=dict(original_files=257880,original_bytes_approx=15.45*2**30),selected_files=len(rows),selected_bytes=sum(x['bytes'] for x in rows),reason_bytes=dict(reasons),raw_images=['Golden','ng-128','ng-135'],report_photos=100,report_candidates=8335,excluded=['Unselected raw test photos','Historical model versions','Old full reports and repeated crops','Intermediate feature caches','Browser profile and runtime caches','Original station acquisition/results databases','Python environments and installers'],limits=['Full100 fresh regression cannot run from this lean bundle; fetch original corpus separately when required','Windows proof hashes are historical evidence, not a Mac execution attestation','Production defaults remain47+65 paired;51+90 is experimental only'],files=rows)
    write(dest/'archives/LEAN-SCOPE.json',scope)
    result=transfer.validate_station(dest);assert result['ok'],result
    write(dest.parent/'selection-summary.json',{k:v for k,v in scope.items() if k!='files'})
    print(json.dumps(dict(validation=result,files=len(rows),MiB=round(scope['selected_bytes']/2**20,2),categories_MiB={k:round(v/2**20,2) for k,v in reasons.items()}),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
