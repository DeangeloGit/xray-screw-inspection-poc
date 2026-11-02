import json
from pathlib import Path
from collections import defaultdict
import numpy as np
from normal_variation import separate
ROOT=Path('workspace/windows-check/diagnostics/collected-data')

def run():
 plan=json.loads((ROOT/'benchmark-plan.json').read_text(encoding='utf-8'))['items']
 rows=[json.loads(p.read_text(encoding='utf-8')) for p in (ROOT/'cache').glob('*/baseline.json')]
 models=sorted({r['model'] for r in rows});summary=[]
 for model in models:
  good=sorted([r for r in plan if r['model']==model and r['label']=='OK' and r['split']=='development' and 'error' not in r],key=lambda r:r['relative'])
  bank=[];units=set()
  for r in good:
   unit=Path(r['path']).stem.split('_')[0]
   if unit in units:continue
   units.add(unit);bank.append(r)
   if len(bank)==6:break
  if len(bank)<2 or any(not (ROOT/'cache'/r['sha256']/'aligned.npz').exists() for r in bank):continue
  normals=[(r['sha256'],np.load(ROOT/'cache'/r['sha256']/'aligned.npz')['target']) for r in bank]
  bankids={r['sha256'] for r in bank}
  targets=[r for r in rows if r['model']==model and r['sha256'] not in bankids and Path(r['path']).stem.split('_')[0] not in units and 'error' not in r]
  for row in targets:
   target=np.load(ROOT/'cache'/row['sha256']/'aligned.npz')['target']
   kept,explained=separate(row['candidates'],target,normals,.13)
   summary.append(dict(sha256=row['sha256'],relative=row['relative'],split=row['split'],label=row['label'],before=len(row['candidates']),after=len(kept),bank=[b['relative'] for b in bank],explained=explained))
 print([(r['relative'],r['split'],r['before'],r['after']) for r in summary],flush=True)
 (ROOT/'normal-bank-experiment.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':run()
