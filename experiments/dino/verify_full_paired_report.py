"""Validate report completeness, all local links/anchors, totals, and frozen inputs."""
import sys,json,hashlib
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import unquote
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.dino.full_paired_run import OUT,read,digest
class Parser(HTMLParser):
    def __init__(self):super().__init__();self.links=[];self.ids=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.append(a['id'])
        for k in ('href','src'):
            if k in a:self.links.append(a[k])
def main():
    cases=read(OUT/'cases.json');rows=read(OUT/'rows.json');s=read(OUT/'summary.json');plan=read(OUT/'plan.json')
    assert len(cases)==len({z['key'] for z in cases})==2793
    assert len(rows)==190 and sum(not r['is_reference'] for r in rows)==186
    assert len(list((OUT/'photos').glob('*.html')))==190
    for label in ['OK','NG']:
        zs=[z for z in cases if z['label']==label];rs=[r for r in rows if r['label']==label and not r['is_reference']]
        for method in ['old','new','paired']:
            expected=sum(z[method+'_keep'] for z in zs);actual=s[label][method]
            assert actual['kept']==expected and actual['removed']==len(zs)-expected
            assert actual['zero_images']==sum(not any(z['sha']==r['sha256'] and z[method+'_keep'] for z in zs) for r in rs)
    assert s['OK']['old']['kept']==0 and s['NG']['old']['kept']==330
    for z in cases:
        assert z['paired_keep']==(z['target']['screw'] and not z['reference']['screw'])
        assert (OUT/'images'/(z['key']+'.jpg')).exists()
    parsers={}
    def parse(f):
        if f not in parsers:
            p=Parser();p.feed(f.read_text(encoding='utf-8'));assert len(p.ids)==len(set(p.ids)),f;parsers[f]=p
        return parsers[f]
    pages=list(OUT.glob('*.html'))+list((OUT/'photos').glob('*.html'))
    for f in pages:
        for link in parse(f).links:
            if '://' in link:continue
            name,sep,anchor=link.partition('#');dest=(f.parent/unquote(name)).resolve() if name else f.resolve()
            assert dest.exists(),(f,link)
            if anchor:assert anchor in parse(dest).ids,(f,link)
    index=read(OUT/'review-index.json')
    assert len(index)==2793 and {z['key'] for z in index}=={z['key'] for z in cases}
    for machine,label in [('MPT10','OK'),('MPT12','OK'),('KPH33','OK'),('MPT11','NG')]:
        stem='good' if label=='OK' else 'bad'
        for category in ['wire','edge','component','structure','unknown']:
            page=OUT/f'{stem}-{machine}-{category}.html'
            expected={'case-'+z['key'] for z in index if z['machine']==machine and z['label']==label and z['category']==category}
            actual={key for key in parse(page).ids if key.startswith('case-')}
            assert expected==actual,(page,len(expected),len(actual))
    for r in rows:
        page=OUT/'photos'/(r['sha256']+'.html');text=page.read_text(encoding='utf-8')
        assert '返回此機種' in text and '本張分類' in text
        expected={'case-'+z['key'] for z in index if z['sha']==r['sha256']}
        assert expected=={key for key in parse(page).ids if key.startswith('case-')}
        if expected:assert '查看同類案例' in text
    assert all(digest(Path(p))==v for p,v in plan['hashes'].items())
    print('PASS',len(pages),'HTML pages, 190 photos, 2793 candidate cards/images, three-way totals, all links/anchors, preserved inputs and active selection')
if __name__=='__main__':main()
