"""Verify that every reported candidate stays in its actual decision column."""
import json,sys
from pathlib import Path
from html.parser import HTMLParser
class Parser(HTMLParser):
    def __init__(self):super().__init__();self.stack=[];self.items={};self.columns=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='section':
            self.stack.append(a.get('data-result'))
            if a.get('data-result'):self.columns.append(a['data-result'])
        if tag=='article' and a.get('id','').startswith('case-'):
            key=a['id'][5:];assert key not in self.items;self.items[key]=next((v for v in reversed(self.stack) if v),None)
    def handle_endtag(self,tag):
        if tag=='section':self.stack.pop()
def main():
    root=Path(sys.argv[1]);cases=json.loads((root/'cases.json').read_text(encoding='utf8'));count=0;pages=0
    for path in list((root/'report').glob('photo-*.html'))+list((root/'report').glob('category-*.html')):
        p=Parser();p.feed(path.read_text(encoding='utf8'));field='photo' if path.stem.startswith('photo-') else 'category';value=path.stem.split('-',1)[1];expected={c['key']:c for c in cases if c[field]==value};assert set(p.items)==set(expected),(path,len(p.items),len(expected))
        assert all(p.columns[i:i+2]==['exclude','keep'] for i in range(0,len(p.columns),2)),path
        for key,outcome in p.items.items():
            keep=expected[key]['keep'];keep=keep['pilot'] if isinstance(keep,dict) else keep;assert outcome==('keep' if keep else 'exclude'),(path,key,outcome)
        count+=len(p.items);pages+=1
    result=dict(status='passed',pages=pages,candidate_occurrences=count,unique_candidates=len(cases),left='exclude',right='keep',each_candidate_in_both_photo_and_category=count==2*len(cases));assert result['each_candidate_in_both_photo_and_category']
    (root/'column-verification.json').write_text(json.dumps(result,indent=2),encoding='utf8');print(result)
if __name__=='__main__':main()
