"""Validate complete reports, files, counts, preserved inputs, and frozen engine."""
import json,hashlib
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import unquote,urlsplit

PROJECT=Path(__file__).resolve().parents[2]
OUT=PROJECT/'workspace/windows-check/diagnostics/v10-full-evaluation-20261103'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[];self.articles=0;self.svgs=0
    def handle_starttag(self,tag,attrs):
        if tag=='article':self.articles+=1
        if tag=='svg':self.svgs+=1
        for key,value in attrs:
            if key in ('href','src') and value:self.links.append(value)

def main():
    plan=read(OUT/'plan.json');rows=read(OUT/'results.json');summary=read(OUT/'summary.json')
    assert summary['complete'] and len(rows)==len(plan['items'])==190
    assert sum(r['is_reference'] for r in rows)==4
    assert len({r['sha256'] for r in rows})==190
    assert summary['non_reference']['images']==186
    assert summary['good']['images']==139 and summary['bad']['images']==47
    assert all(digest(PROJECT/name)==sha for name,sha in plan['code'].items())
    assert all(digest(r['path'])==r['sha256'] for r in rows)
    checked_links=0
    for file in list(OUT.glob('*.html'))+list((OUT/'photos').glob('*/report.html')):
        parser=Links();parser.feed(file.read_text(encoding='utf-8'))
        for link in parser.links:
            parts=urlsplit(link)
            if parts.scheme or not parts.path:continue
            target=(file.parent/unquote(parts.path)).resolve()
            assert target.exists(),(file,link)
            checked_links+=1
        if file.parent.parent.name=='photos':
            row=read(file.parent/'evaluation.json')
            if row['success']:
                result=read(file.parent/'result.json')
                assert result['version']==10 and result['threshold']==.13
                assert result['model']['fingerprint']==plan['model']['fingerprint']
                assert result['model']['backend']=='clip_onnx' and not result['model']['error']
                assert parser.articles==row['count'] and parser.svgs==2*row['count']
                assert row['high']+row['review']==row['count']
                assert row['ai_screw']+row['ai_uncertain']+row['ai_non_screw']+row['ai_error']==row['count']
                assert all(c['classification']['action']=='manual_review' for c in result['candidates'])
    validation=dict(passed=True,images=190,non_reference_tests=186,reference_self_checks=4,
                    reports=193,validated_local_links=checked_links,
                    frozen_code_unchanged=True,original_inputs_unchanged=True)
    (OUT/'validation.json').write_text(json.dumps(validation,indent=2))
    print(json.dumps(validation))

if __name__=='__main__':main()
