"""Score both-class preprocessing controls using recorded fresh DINO features."""
from example_audit_probe import *
def main():
    snap=ModelManager(ROOT/'models',allow_cpu=True,execution_override='gpu').snapshot('dino-paired-optimized-47-20261104-r3');assert not snap.error
    bp=OUT/'letterbox-112-bank.npz'
    if not bp.exists():
        e=read(ROOT/'models/dino-paired-optimized-47-20261104-r3/examples.json');neg=[]
        for i in snap.manifest['example_bank']['normal']['ids']:
            a=np.asarray(Image.open(ROOT/'models/dino-paired-optimized-47-20261104-r3/examples'/e[i]['file']).convert('L'),np.float32)/255
            neg.append(example_features(snap.manifest,snap.session,square(a)))
        np.savez_compressed(bp,bank=np.concatenate([np.load(OUT/'letterbox-47-bank.npz')['bank'][:47],neg]))
    bank=np.load(bp)['bank'];rows=[]
    for p in sorted((OUT/'all-features').glob('*.json')):
        rr=read(p);cache=np.load(p.with_suffix('.npz'))
        for z in rr:
            for pad in (2,4,8,12):
                for mode in ('center','letterbox'):
                    src=z['variants'][f'{mode}-{pad}-old'];z['variants'][f'{mode}-{pad}-allbank']={s:dict(score(cache[v['input_sha256']],bank,47),input_sha256=v['input_sha256']) for s,v in src.items()}
            rows.append(z)
    save(OUT/'all-crop-bank-scores.json',rows)
    cases=read(BASE/'cases.json');ci={c['key']:c for c in cases};basekeep={c['key'] for c in cases if c['keep']['pilot']};summaries=[]
    variants=[(f'{mode}-{pad}-{bankname}',[f'{mode}-{pad}-{bankname}']) for mode in ('center','letterbox') for pad in (2,4,8,12) for bankname in ('old','letterbox','allbank')]
    variants += [(f'consensus-{mode}-{bankname}',[f'{mode}-{p}-{bankname}' for p in (2,4,8,12)]) for mode in ('center','letterbox') for bankname in ('old','letterbox','allbank')]
    for name,keys in variants:
        # All trial scoring preserves baseline alarms; no per-photo/answer gate.
        added={f'{z["photo"]}-{z["id"]}' for z in rows if not z['baseline_keep'] and all(z['variants'][k]['target']['margin']>=0 and z['variants'][k]['reference']['margin']<0 for k in keys)}
        keep=basekeep|added;hits={(ci[k]['photo'],a) for k in keep for a in ci[k]['answers']};false=[k for k in added if not ci[k]['answers'] and not ci[k]['is_reference']]
        s=dict(variant=name,hits=len(hits),new_alarms=len(added),new_unmatched=len(false),unmatched=50+len(false),new_answer4=sum((str(p),4) in hits for p in range(128,138)),new_keys=sorted(added),false_keys=sorted(false),reference_new=[k for k in added if ci[k]['is_reference']]);summaries.append(s)
        print(name,'HITS',s['hits'],'a4',s['new_answer4'],'NEW_OUTSIDE',len(false),'new',len(added),flush=True)
    save(OUT/'ablation-summary.json',summaries)
    checked=[]
    for bankname in ('old','letterbox','allbank'):
        for consensus in ('unanimous','three_of_four','mean_four'):
            added=[];eligible=[]
            for z in rows:
                c=ci[f'{z["photo"]}-{z["id"]}'];meta=c.get('correspondence_experiment') or {}
                if z['baseline_keep'] or c['rules'] or meta.get('recheck')!='complete_contour' or c['paired_evidence']['target']['label']!='non_screw':continue
                eligible.append(c['key']);pairs=[z['variants'][f'letterbox-{p}-{bankname}'] for p in (2,4,8,12)]
                votes=sum(v['target']['margin']>=0 for v in pairs)
                keep=votes>=({'unanimous':4,'three_of_four':3,'mean_four':0}[consensus]) and np.mean([v['target']['margin'] for v in pairs])>=0 and all(v['reference']['margin']<0 for v in pairs)
                if keep:added.append(c['key'])
            hits={(ci[k]['photo'],a) for k in basekeep|set(added) for a in ci[k]['answers']};outside=[k for k in added if not ci[k]['answers']]
            z=dict(bank=bankname,consensus=consensus,eligible=eligible,added=added,hits=len(hits),new_unmatched=outside,three_of_four_definition='At least three positive target views, nonnegative mean, all four reference views negative. Margins use original zero cutoff. Existing structural and matched-reference exclusions are not overridden.')
            checked.append(z);print('GATED',bankname,consensus,'HITS',len(hits),'OUTSIDE',outside,'ADDED',added,flush=True)
    save(OUT/'gated-ablation-summary.json',checked)
    save(OUT/'ablation-coverage.json',dict(candidates=len(rows),photos=[p.stem for p in sorted((OUT/'all-features').glob('*.json'))],original_candidates=1345,unchanged_B_route_candidates=987,all2332_covered=len(rows)==1345 and len(list((OUT/'all-features').glob('*.json')))==11,scope='Fresh feature extraction for original1345; existing987 B-route candidates remain unchanged. No independent scans.'))
if __name__=='__main__':main()
