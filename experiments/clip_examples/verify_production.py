import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from detector import detect
from model_manager import manager
WORK=ROOT/'workspace/windows-check';OUT=WORK/'diagnostics/clip-screw-examples'
cases=json.loads((WORK/'ai-trials/cases.json').read_text(encoding='utf-8'))
checks=[]
for case in cases:
 result=(json.loads((OUT/'production'/case['name']/'result.json').read_text(encoding='utf-8')) if '--cached' in sys.argv else detect(Path(case['reference']),Path(case['target']),case['name'],threshold=case['threshold'],output_directory=OUT/'production'/case['name']))
 for index,(x0,y0,x1,y1) in enumerate(case['known_regions'],1):
  found=[]
  for c in result['candidates']:
   x,y,w,h=(c[k] for k in ('x','y','w','h'));inter=max(0,min(x+w,x1)-max(x,x0))*max(0,min(y+h,y1)-max(y,y0));union=w*h+(x1-x0)*(y1-y0)-inter
   # Match the historical annotation protocol: retain an overlapping candidate.
   # This checks filtering preservation, not full-object localization accuracy.
   if inter>0:found.append(c['id'])
  assert found,(case['name'],index)
  checks.append(dict(sample=case['name'],region=index,retained_ids=found))
 print(case['name'],'retained',len(case['known_regions']), 'candidates',result['proposal_count'],flush=True)
(OUT/'production-check.json').write_text(json.dumps(dict(model=manager.snapshot().info(),known_regions=checks),ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS: fresh detector output retains all',len(checks),'known screw regions')
