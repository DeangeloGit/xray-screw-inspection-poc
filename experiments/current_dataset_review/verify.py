"""Audit all report counts, filtering partitions, links and frozen inputs."""
import sys,json,hashlib
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit,unquote
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'workspace/windows-check/diagnostics/v11-examples-full-evaluation-20261103'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
class Parser(HTMLParser):
 def __init__(self):super().__init__();self.links=[];self.cards=0;self.svg=0
 def handle_starttag(self,tag,attrs):
  self.cards+=tag=='article';self.svg+=tag=='svg'
  self.links += [v for k,v in attrs if k in ('src','href') and v]
def main():
 plan=read(OUT/'plan.json');rows=read(OUT/'report-rows.json');summary=read(OUT/'summary.json')
 assert len(rows)==190 and summary['tests']==186 and summary['good']['images']==139 and summary['bad']['images']==47
 assert sum(r['is_reference'] for r in rows)==4 and all(r['success'] for r in rows)
 assert all(digest(ROOT/name)==sha for name,sha in plan['code'].items())
 assert all(digest(r['path'])==r['sha256'] for r in rows)
 baseline={r['sha256']:r for r in read(ROOT/'workspace/windows-check/diagnostics/v10-full-evaluation-20261103/results.json')}
 review=read(OUT/'good-review-index.json')
 ngreview=read(OUT/'bad-review-index.json')
 extra=[OUT/n for n in review['pages'] if n!='good.html']+[OUT/n for n in ngreview['pages'] if n!='bad.html']
 checked=0;pages=[OUT/n for n in ('index.html','good.html','bad.html','issues.html')]+extra
 for row in rows:
  folder=OUT/'photos'/row['sha256'];result=read(folder/'result.json');pages.append(folder/'report.html')
  assert result['version']==11 and result['threshold']==.13
  assert result['model']['fingerprint']==plan['model']['fingerprint'] and not result['model']['error']
  assert result['pre_ai_count']==result['proposal_count']+result['filtered_count']==baseline[row['sha256']]['count']
  assert result['high_count']+result['review_count']==result['proposal_count']
  kept,removed=result['candidates'],result['filtered_candidates'];allc=kept+removed
  assert len({c['id'] for c in allc})==result['pre_ai_count']
  assert all(c['classification']['action']=='manual_review' for c in kept)
  assert all(c['classification']['action']=='discard' and c['classification']['filter_recommendation']=='non_screw_suggestion' for c in removed)
  assert all(c['classification']['status']=='active' for c in allc)
  assert row['ai_screw']+row['ai_uncertain']==row['count']
  parser=Parser();parser.feed((folder/'report.html').read_text(encoding='utf-8'))
  assert parser.cards==result['pre_ai_count'] and parser.svg==2*result['pre_ai_count']
 for file in pages:
  parser=Parser();parser.feed(file.read_text(encoding='utf-8'))
  for link in parser.links:
   parts=urlsplit(link)
   if parts.scheme or not parts.path:continue
   assert (file.parent/unquote(parts.path)).resolve().exists(),(file,link)
   checked+=1
 assert len(pages)==194+len(extra) and summary['historical_retained']==summary['historical_regions']==8
 assert summary['known_batch_retained']==summary['known_batch_regions']==2
 assert review['total']==len(review['items'])==sum(review['categories'].values())==106
 for item in review['items']:
  name=f'good-{item["machine"]}-{item["category"]}.html'
  text=(OUT/name).read_text(encoding='utf-8')
  assert text.count(f'id="case-{item["sha"]}-{item["id"]}"')==1
 assert ngreview['total']==len(ngreview['items'])==sum(ngreview['categories'].values())==2665
 assert len({(z['sha'],z['id']) for z in ngreview['items']})==2665
 texts={n:(OUT/n).read_text(encoding='utf-8') for n in ngreview['pages']}
 for z in ngreview['items']:
  text=texts[f'bad-{z["machine"]}-{z["category"]}.html']
  assert text.count(f'id="case-{z["sha"]}-{z["id"]}"')==1
 issues=read(OUT/'visual-issues.json')
 assert len(issues)==6
 for issue in issues:
  result=read(OUT/'photos'/issue['sha256']/'result.json')
  c=next(c for c in result['filtered_candidates'] if c['id']==issue['candidate_id'])
  assert c['classification']['label']==issue['ai_label'] and not issue['retained_overlapping_ids']
 verification=dict(visual_issue_examples=6,passed=True,images=190,tests=186,reports=len(pages),links=checked,source_and_engine_unchanged=True,pre_ai_counts_match_previous_run=True,known_batch_regions_retained=2,historical_regions_retained=8)
 (OUT/'validation.json').write_text(json.dumps(verification,indent=2));print(json.dumps(verification))
if __name__=='__main__':main()
