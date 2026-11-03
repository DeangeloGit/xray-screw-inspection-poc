"""Verify accounting, model identity, and local report links."""
import json
from pathlib import Path
from html.parser import HTMLParser
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'workspace/windows-check/diagnostics/dino-full-evaluation-20261103'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
def main():
 rows=read(OUT/'results.json');plan=read(OUT/'plan.json');summary=read(OUT/'summary.json');assert len(rows)==190 and sum(not r['is_reference'] for r in rows)==186
 total=0
 for r in rows:
  assert r['success'];result=read(OUT/'photos'/r['sha256']/'result.json')
  kept=result['candidates'];removed=result['filtered_candidates'];allc=kept+removed
  assert len(allc)==r['pre_ai_count']==len({c['id'] for c in allc})
  assert len(kept)==r['count'] and len(removed)==r['filtered_count']
  assert result['model']['fingerprint']==plan['model']['fingerprint']
  assert all(c['classification']['status']=='active' for c in allc)
  assert all(c['classification']['action']=='discard' for c in removed)
  assert all(c['classification']['action']!='discard' for c in kept)
  total+=len(allc)
 assert summary['good']['images']==139 and summary['bad']['images']==47
 missing=[];count=0
 class Links(HTMLParser):
  def __init__(self,base):super().__init__();self.base=base
  def handle_starttag(self,tag,attrs):
   for key,value in attrs:
    if key in ('src','href') and value and not value.startswith(('http','#','data:')):
     f=(self.base/value.split('#')[0]).resolve()
     if not f.exists():missing.append(str(f))
 for page in OUT.rglob('*.html'):
  Links(page.parent).feed(page.read_text(encoding='utf-8'));count+=1
 assert not missing,missing[:10]
 print('PASS',len(rows),'photos,',total,'candidate decisions,',count,'HTML pages; accounting, model identity and links')
if __name__=='__main__':main()
