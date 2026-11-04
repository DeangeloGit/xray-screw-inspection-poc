"""Follow-up fixed equal weighting, without fitting weights to the test cases."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.dino.fixed_crop_recognition_pilot import OUT,read,save
def main():
 rule=dict(method='equal_average_of_margins',components=['eight_views_cls','patch_mean'],weights=[.5,.5],threshold=0,
  note='Follow-up suggested by complementary errors on same development cases; not an independent confirmation; weights fixed at equal share without grid search.',
  classify_each_side_independently=True,keep='target screw AND reference non_screw')
 save(OUT/'equal-vote-rule.json',rule)
 rows=read(OUT/'results.json');result=[]
 for r in rows:
  rec=dict(number=r['number'],key=r['key'],protocols={})
  for protocol,methods in r['protocols'].items():
   p={}
   for side in ['reference','target']:
    scores=[methods[k][side]['margin'] for k in rule['components']];margin=sum(scores)/2
    p[side]=dict(screw=margin>=0,margin=margin,component_margins=scores)
   p['keep']=p['target']['screw'] and not p['reference']['screw'];rec['protocols'][protocol]=p
  result.append(rec)
 summary={}
 for protocol in ['all_47_65','exclude_known_overlap']:
  pairs=[r['protocols'][protocol] for r in result]
  summary[protocol]=dict(screw_pairs_correct=sum(p['keep'] for p in pairs[:2]),
   screw_pair_labels=[dict(reference=p['reference']['screw'],target=p['target']['screw']) for p in pairs[:2]],
   normal_alerts=[i+1 for i,p in enumerate(pairs) if i>=2 and p['keep']],
   normal_both_non_screw=sum(not p['reference']['screw'] and not p['target']['screw'] for p in pairs[2:]))
 save(OUT/'equal-vote-results.json',result);save(OUT/'equal-vote-summary.json',summary)
 print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':main()
