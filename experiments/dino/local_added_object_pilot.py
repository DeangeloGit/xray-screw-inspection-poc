"""Read-only offline paired-image pilot. Never imports the server or writes models.

Selection is frozen before computing new scores; all selected cases are reported.
"""
import json, hashlib, math, sys
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'workspace/windows-check/diagnostics/dino-full-evaluation-20261103'
FULL=ROOT/'workspace/windows-check/diagnostics/dino-47-paired-full-20261103'
OUT=ROOT/'workspace/added-object-pilot-20261103'
PREVIEW=ROOT/'workspace/windows-check/state/tuning-previews/0727ad8422264ea29813b0fd886b2e15'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def save(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def font(n):return ImageFont.truetype('C:/Windows/Fonts/msjh.ttc',n)

def prepare():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'plan.json').exists():raise RuntimeError('Frozen plan already exists')
    cases=read(FULL/'cases.json');bykey={z['key']:z for z in cases}
    res=read(PREVIEW/'result.json');cs=res['candidates']+res['filtered_candidates']
    selected=[]
    for i,title in [(94,'使用者指出：新增斜螺絲'),(34,'使用者指出：新增圓頭螺絲')]:
        c=next(c for c in cs if c['id']==i)
        selected.append(dict(key=f'current-{i}',id=i,c=c,name='CND6440DTD_2026_11_03_09_57_57_32.tiff',machine='MPT12',category='新增螺絲',expected='new',basis='使用者確認',title=title,source=str(PREVIEW),paired_keep=False))
    key='7fabdc13f66ab8f99de8d369a8de6b672c4e2d94eb9565802953e082b2a8badb-80'
    z=bykey[key]
    selected.append(dict(z,category='元件外觀',expected='normal',basis='使用者先前指出的原有物件誤報',title='先前圖一：參照已經有的圓形物件',source=str(BASE/'photos'/z['sha'])))
    visual=read(ROOT/'experiments/current_dataset_review/good_visual_categories.json')
    # Same selection order as the pre-existing visual catalogue, diverse locations.
    for category,limit in [('wire',8),('edge',2),('component',2),('structure',2)]:
        chosen=[]
        for v in visual:
            if v['category']!=category:continue
            z=bykey.get(f"{v['sha']}-{v['id']}")
            if not z or z['label']!='OK':continue
            cx,cy=v['x']+v['w']/2,v['y']+v['h']/2
            if any(a['machine']==v['machine'] and math.hypot(cx-a['x']-a['w']/2,cy-a['y']-a['h']/2)<70 for a in chosen):continue
            chosen.append(v)
            name={'wire':'線材','edge':'板件邊界','component':'元件外觀','structure':'U 形結構'}[category]
            selected.append(dict(z,category=name,expected='normal',basis='既有良品資料夾；外觀類型沿用先前目視分類，移動原因尚需看圖確認',title=f'良品對照：{name}',source=str(BASE/'photos'/z['sha'])))
            if len(chosen)==limit:break
    protected={ROOT/'models/active.json',ROOT/'config/station.json'}
    protected.update((ROOT/'models/dino-paired-47-20261103').rglob('*'))
    protected.update(ROOT.glob('*.py'))
    for z in selected:
        for f in ['reference.png','aligned.png','result.json']:protected.add(Path(z['source'])/f)
    hashes={str(p):digest(p) for p in sorted(protected) if p.is_file()}
    save(OUT/'plan.json',dict(scope='兩組指定新增螺絲與固定正常對照；非整批準確率',selection='指定兩組＋先前圖一＋既有良品目視分類順序，各類相同機種中心距離至少70px；不看新規則分數選樣',cases=selected,hashes=hashes))
    for start in range(0,len(selected),6):
        batch=selected[start:start+6];im=Image.new('RGB',(1000,len(batch)*235),'white');d=ImageDraw.Draw(im)
        for row,z in enumerate(batch):
            c=z['c'];cx,cy=c['x']+c['w']/2,c['y']+c['h']/2
            side=max(100,c['w']+50,c['h']+50);box=(round(cx-side/2),round(cy-side/2),round(cx+side/2),round(cy+side/2))
            d.text((8,row*235+5),f"{start+row+1}. {z['machine']} {z['category']} #{z['id']}",font=font(20),fill='black')
            for j,f in enumerate(['reference.png','aligned.png']):
                p=Image.open(Path(z['source'])/f).convert('RGB').crop(box);pd=ImageDraw.Draw(p);pd.rectangle((c['x']-box[0],c['y']-box[1],c['x']+c['w']-box[0],c['y']+c['h']-box[1]),outline='#ff304b',width=1)
                im.paste(p.resize((210,200)),(510+j*240,row*235+30))
            d.text((8,row*235+40),z['key'][:30],font=font(14),fill='black')
        im.save(OUT/f'selection-{start//6+1}.jpg')
    print(json.dumps({'selected':len(selected),'normal':len(selected)-2,'keys':[z['key'] for z in selected]}))

RULES=dict(context_padding=52,excluded_padding=12,search_radius=12,
           minimum_context_correlation=.75,change_threshold=.10,
           minimum_component_area=12,new_dark_share=.80,
           balanced_dark_share=[.25,.75],version='exploratory-v1')

def compare(ref,target,c):
    x,y,w,h=(c[k] for k in ('x','y','w','h'));p=RULES['context_padding'];r=RULES['search_radius'];e=RULES['excluded_padding']
    x0,y0=max(r,x-p),max(r,y-p);x1,y1=min(ref.shape[1]-r,x+w+p),min(ref.shape[0]-r,y+h+p)
    patch=target[y0:y1,x0:x1].astype('float32')
    mask=np.ones(patch.shape,'uint8');mask[max(0,y-e-y0):y+h+e-y0,max(0,x-e-x0):x+w+e-x0]=0
    search=ref[y0-r:y1+r,x0-r:x1+r].astype('float32')
    corr=cv2.matchTemplate(search,patch,cv2.TM_CCOEFF_NORMED,mask=mask);corr[~np.isfinite(corr)]=-1
    _,score,_,point=cv2.minMaxLoc(corr);dx,dy=point[0]-r,point[1]-r
    # Never allow a borderline/context-poor match to justify an exclusion.
    reliable=score>=RULES['minimum_context_correlation'] and max(abs(dx),abs(dy))<r
    normal=ref[y0+dy:y1+dy,x0+dx:x1+dx].astype('float32');weights=mask.astype('float32')
    for _ in range(4):
        mass=max(float(weights.sum()),.001);mx=float((weights*normal).sum()/mass);my=float((weights*patch).sum()/mass)
        gain=float(np.clip((weights*(normal-mx)*(patch-my)).sum()/max(float((weights*(normal-mx)**2).sum()),.001),.6,1.6))
        offset=float(np.clip(my-gain*mx,-.25,.25));fitted=np.clip(gain*normal+offset,0,1)
        error=np.abs(fitted-patch);weights=mask*np.minimum(1,.04/np.maximum(error,.0001))**2
    roi=(slice(y-e-y0,y+h+e-y0),slice(x-e-x0,x+w+e-x0));delta=(fitted-patch)[roi]
    positive=np.maximum(delta-RULES['change_threshold'],0);negative=np.maximum(-delta-RULES['change_threshold'],0)
    dark=float(positive.sum());light=float(negative.sum());share=dark/max(dark+light,.00001)
    n,labels,stats,centers=cv2.connectedComponentsWithStats((delta>RULES['change_threshold']).astype('uint8'))
    overlaps=set(np.unique(labels[e:e+h,e:e+w]))-{0}
    area=max([int(stats[i,cv2.CC_STAT_AREA]) for i in overlaps],default=0)
    p95=float(np.percentile(np.abs(delta),95));outcome='uncertain'
    if reliable:
        if area<RULES['minimum_component_area'] and p95<=.10:outcome='explained'
        elif area>=RULES['minimum_component_area'] and share>=RULES['new_dark_share']:outcome='new_alert'
        elif .25<=share<=.75:outcome='movement_hint'
    metrics=dict(outcome=outcome,context_reliable=reliable,context_correlation=score,dx=dx,dy=dy,gain=gain,offset=offset,dark_mass=dark,light_mass=light,dark_share=share,component_area=area,absolute_p95=p95)
    return metrics,delta,fitted[roi],patch[roi]

def evaluate():
    plan=read(OUT/'plan.json');rulefile=OUT/'rules-v1.json'
    if rulefile.exists():assert read(rulefile)==RULES,'Never silently change a tested rule'
    else:save(rulefile,RULES)
    results=[];(OUT/'images').mkdir(exist_ok=True)
    for n,z in enumerate(plan['cases'],1):
        arrays=[np.asarray(Image.open(Path(z['source'])/f).convert('L'),dtype='float32')/255 for f in ['reference.png','aligned.png']]
        m,diff,matched,tar=compare(*arrays,z['c']);results.append(dict(number=n,key=z['key'],**m))
        # Raw pair and matched residual are separate; the report labels them explicitly.
        for label,arr in [('matched',matched),('target',tar)]:Image.fromarray(np.uint8(np.clip(arr,0,1)*255)).save(OUT/'images'/f'{n}-{label}.png')
        vis=np.ones((*diff.shape,3),dtype='uint8')*240;vis[diff>.10]=[224,58,58];vis[diff<-.10]=[38,115,210]
        Image.fromarray(vis).save(OUT/'images'/f'{n}-change.png')
        print(n,z['category'],m['outcome'],'corr',round(m['context_correlation'],3),'shift',m['dx'],m['dy'],'darkshare',round(m['dark_share'],3),'area',m['component_area'],'p95',round(m['absolute_p95'],3))
    save(OUT/'results-v1.json',results)
    assert all(digest(Path(p))==v for p,v in plan['hashes'].items()),'Protected data changed'
    save(OUT/'preservation.json',dict(verified_files=len(plan['hashes']),unchanged=True))

MATCH_RULES=dict(version='exploratory-v2',crop_padding=12,search_radius=32,
                 similar_at=.75,no_match_below=.45,
                 description='Candidate plus original AI padding, no square center crop; local normalized template match, no training.')

def evaluate_match():
    plan=read(OUT/'plan.json');rulefile=OUT/'rules-v2.json'
    if rulefile.exists():assert read(rulefile)==MATCH_RULES
    else:save(rulefile,MATCH_RULES)
    results=[]
    for n,z in enumerate(plan['cases'],1):
        ref,target=[np.asarray(Image.open(Path(z['source'])/f).convert('L'),dtype='float32')/255 for f in ['reference.png','aligned.png']]
        c=z['c'];x,y,w,h=(c[k] for k in ('x','y','w','h'));p=MATCH_RULES['crop_padding'];radius=MATCH_RULES['search_radius']
        x0,y0=max(0,x-p),max(0,y-p);x1,y1=min(ref.shape[1],x+w+p),min(ref.shape[0],y+h+p)
        sx0,sy0=max(0,x0-radius),max(0,y0-radius);sx1,sy1=min(ref.shape[1],x1+radius),min(ref.shape[0],y1+radius)
        patch=target[y0:y1,x0:x1];search=ref[sy0:sy1,sx0:sx1]
        scores=cv2.matchTemplate(search,patch,cv2.TM_CCOEFF_NORMED);scores[~np.isfinite(scores)]=-1
        _,score,_,point=cv2.minMaxLoc(scores);mx,my=sx0+point[0],sy0+point[1]
        boundary=point[0] in (0,scores.shape[1]-1) or point[1] in (0,scores.shape[0]-1)
        outcome='similar_found' if score>=MATCH_RULES['similar_at'] and not boundary else 'no_similar_found' if score<MATCH_RULES['no_match_below'] else 'uncertain'
        result=dict(number=n,key=z['key'],correlation=score,dx=mx-x0,dy=my-y0,boundary=boundary,outcome=outcome,match_box=[mx,my,mx+patch.shape[1],my+patch.shape[0]])
        results.append(result)
        match=ref[my:my+patch.shape[0],mx:mx+patch.shape[1]]
        Image.fromarray(np.uint8(match*255)).save(OUT/'images'/f'{n}-appearance-match.png')
        print(n,z['category'],outcome,round(score,3),'shift',result['dx'],result['dy'])
    save(OUT/'results-v2.json',results)
    assert all(digest(Path(p))==v for p,v in plan['hashes'].items())

DINO_RULES=dict(version='exploratory-v3',same_at=.80,different_below=.60,
               description='Direct cosine similarity of the existing DINO target and reference CLS features; no retraining or bank changes.')

def evaluate_dino():
    sys.path.insert(0,str(ROOT))
    from dino_adapter import embedding,input_image,classify_vector
    import onnxruntime as ort
    plan=read(OUT/'plan.json');rulefile=OUT/'rules-v3.json'
    if rulefile.exists():assert read(rulefile)==DINO_RULES
    else:save(rulefile,DINO_RULES)
    model=ROOT/'models/dino-paired-47-20261103';m=read(model/'manifest.json')
    options=ort.SessionOptions();options.intra_op_num_threads=4
    session=ort.InferenceSession(str(model/'model.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
    cache=np.load(FULL/'features.npz');results=[]
    for n,z in enumerate(plan['cases'],1):
        vectors=[];c=z['c'];x,y,w,h=(c[k] for k in ('x','y','w','h'))
        for label,f in [('reference','reference.png'),('target','aligned.png')]:
            im=Image.open(Path(z['source'])/f).convert('L');crop=np.asarray(im.crop((max(0,x-12),max(0,y-12),min(im.width,x+w+12),min(im.height,y+h+12))),dtype='float32')/255
            inp=input_image(m,crop);inp.save(OUT/'images'/f'{n}-dino-{label}.png')
            k=z.get(label+'_input')
            if k:
                assert hashlib.sha256(np.asarray(inp)[:,:,0].copy().tobytes()).hexdigest()==k,'Cached DINO image mismatch'
                vector=cache[k]
            else:vector=embedding(m,session,crop)
            vectors.append(vector)
        similarity=float(vectors[0]@vectors[1]);outcome='similar' if similarity>=DINO_RULES['same_at'] else 'different' if similarity<DINO_RULES['different_below'] else 'uncertain'
        results.append(dict(number=n,key=z['key'],similarity=similarity,outcome=outcome,target=classify_vector(m,vectors[1]),reference=classify_vector(m,vectors[0])))
        print(n,z['category'],outcome,round(similarity,4))
    save(OUT/'results-v3.json',results)
    assert all(digest(Path(p))==v for p,v in plan['hashes'].items())

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='evaluate':evaluate()
    elif len(sys.argv)>1 and sys.argv[1]=='match':evaluate_match()
    elif len(sys.argv)>1 and sys.argv[1]=='dino':evaluate_dino()
    else:prepare()
