"""Attribute alarms to reference objects with same-input counterfactuals."""
import os,sys,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
OUT=ROOT/'workspace/dino-4r-integrated-bank-20261106';OUT.mkdir(exist_ok=True)
os.environ['XRAY_WORKSPACE']=str(OUT/'runtime');os.environ['XRAY_CONFIG']=str(OUT/'isolated-settings.json')
import numpy as np
from PIL import Image,ImageDraw
read=lambda p:json.loads(p.read_text(encoding='utf8'))
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')
AUDIT=ROOT/'workspace/dino-4r-example-audit-20261106';PRIOR=ROOT/'workspace/dino-4r-crossbatch-20261106';CURRENT=ROOT/'workspace/dino-4r-connector-20261106';NEW=ROOT/'workspace/dino-4r-reference-set-20261106';OLD=ROOT/'workspace/dino-4r-bank-only-20261106'

def scoring(v,bank,n,ids=None):
    sims=[(bank[:,:,0]@v[0]).max(axis=1),bank[:,0,1]@v[1]]
    d=dict(margin=float(np.mean([np.sort(s[:n])[-3:].mean()-np.sort(s[n:])[-3:].mean() for s in sims])))
    if ids:
        d['neighbors']={ch:{label:[dict(id=ids[int(i)],similarity=float(s[i])) for i in ix[np.argsort(s[ix])[-3:][::-1]]] for label,ix in [('screw',np.arange(n)),('normal',np.arange(n,len(s)))]} for ch,s in zip(('whole','local'),sims)}
    return d
def pair(v,b,n,ids=None):
    d={s:scoring(f,b,n,ids) for s,f in v.items()};d['keep']=d['target']['margin']>=0 and d['reference']['margin']<0;return d
def main():
    orig=np.load(OLD/'original-bank.npz')['bank'];clean=np.load(OLD/'positive_clean3-bank.npz')['bank'];newfile=np.load(NEW/'collection/context-bank.npz');new=newfile['bank'];newids=newfile['ids'].tolist();oldids=[f'S{i:02}' for i in range(1,48)]+[f'O-N{i:02}' for i in range(1,66)]
    clean2=clean.copy();clean2[4]=orig[4]
    arms={'original':(orig,47,oldids)}
    for name,b,addpos in [('integrated',orig,True),('clean3_integrated',clean,True),('clean2_integrated',clean2,True),('normal_only',orig,False),('clean3_normal',clean,False),('clean2_normal',clean2,False)]:
        pos=np.concatenate([b[:47],new[:8]]) if addpos else b[:47];ids=oldids[:47]+(newids[:8] if addpos else [])+oldids[47:]+newids[8:];arms[name]=(np.concatenate([pos,b[47:],new[8:]]),len(pos),ids)
    for name,(b,n,ids) in arms.items():np.savez_compressed(OUT/f'{name}-bank.npz',bank=b,n=n,ids=np.array(ids))
    scores=read(AUDIT/'all-crop-bank-scores.json');cases={c['key']:c for c in read(PRIOR/'cases.json')};current={c['key']:c for c in read(CURRENT/'cases.json')};rows=[];attrs=[]
    for photo in map(str,range(128,138)):
        cache=np.load(AUDIT/'all-features'/f'{photo}.npz')
        for q in scores:
            if q['photo']!=photo:continue
            v={s:cache[q['variants']['center-12-old'][s]['input_sha256']] for s in ('reference','target')};key=f'ng-{photo}-{q["id"]}';results={name:pair(v,b,n,ids) for name,(b,n,ids) in arms.items()}
            row=dict(key=key,photo=photo,id=q['id'],box=q['box'],answers=cases[key]['answers'],current_keep=current[key]['keep'],input_sha256={s:q['variants']['center-12-old'][s]['input_sha256'] for s in v},arms=results);rows.append(row)
            if (results['integrated']['keep'] and not results['original']['keep'] and not row['answers']) or key in ('ng-128-22','ng-128-40'):
                b,n,ids=arms['integrated'];cf=[]
                for i,ident in enumerate(ids):
                    if not (ident.startswith('P') or ident.startswith('G') or ident.startswith('N') or ident in ('S05','S07','S20')):continue
                    idx=[j for j in range(len(ids)) if i!=j];p=pair(v,b[idx],n-(i<n));cf.append(dict(id=ident,removed_from='screw' if i<n else 'normal',target_margin=p['target']['margin'],reference_margin=p['reference']['margin'],keep=p['keep'],target_delta=p['target']['margin']-results['integrated']['target']['margin']))
                attrs.append(dict(key=key,box=q['box'],answers=row['answers'],current_keep=row['current_keep'],original=results['original'],integrated=results['integrated'],leave_one_out=cf))
    oldhits={(r['photo'],a) for r in rows if r['arms']['original']['keep'] for a in r['answers']};summary=[]
    for name in arms:
        hits={(r['photo'],a) for r in rows if r['arms'][name]['keep'] for a in r['answers']};s=dict(arm=name,raw_hits=len(hits),lost=sorted(oldhits-hits),unmatched=sum(r['arms'][name]['keep'] and not r['answers'] for r in rows),new_unmatched=[r['key'] for r in rows if r['arms'][name]['keep'] and not r['arms']['original']['keep'] and not r['answers']],pair40=next(r for r in rows if r['key']=='ng-128-40')['arms'][name]['target']['margin']);summary.append(s);print('ARM',name,'hits',len(hits),'lost',s['lost'],'outside',s['unmatched'],'new',len(s['new_unmatched']),'40',s['pair40'],flush=True)
    save(OUT/'fixed-query-scores.json',rows);save(OUT/'fixed-query-summary.json',summary);save(OUT/'attribution.json',attrs)
    print('ATTR',[(r['key'],[(a['id'],round(a['target_delta'],4),a['keep']) for a in sorted(r['leave_one_out'],key=lambda a:a['target_delta'])[:3]]) for r in attrs],flush=True)
    # Contact sheet of all newly retained unmatched candidates, actual crop pair.
    targets=[a for a in attrs if a['key'] not in ('ng-128-22','ng-128-40')]
    for start in range(0,len(targets),8):
        subset=targets[start:start+8];im=Image.new('RGB',(1200,230*((len(subset)+2)//3)),'white');d=ImageDraw.Draw(im)
        for k,z in enumerate(subset):
            x,y,w,h=z['box'];photo='-'.join(z['key'].split('-')[:2]);xx=k%3*400;yy=k//3*230;d.text((xx+4,yy+4),z['key']+' '+str(z['box']),fill='black')
            for j,s in enumerate(('reference','aligned')):
                a=Image.open(PRIOR/'runs'/photo/f'{s}.png').convert('RGB');pad=25;crop=a.crop((x-pad,y-pad,x+w+pad,y+h+pad));dr=ImageDraw.Draw(crop);dr.rectangle((pad,pad,pad+w,pad+h),outline='red',width=1);crop.thumbnail((190,190));im.paste(crop,(xx+j*195+4,yy+30))
        im.save(OUT/f'new-alarms-{start}.png')
if __name__=='__main__':main()
