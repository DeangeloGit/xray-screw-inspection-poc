"""Conservative decision tests; optional saved-score replay is not independent validation."""
import json
from pathlib import Path
import sys
from model_adapters import clip_decision


def run():
    labels=['screw','hole']
    assert clip_decision(labels,[.3,.3])['filter_recommendation']=='keep'
    assert clip_decision(labels,[.31,.3])['label']=='screw'
    assert clip_decision(labels,[.3,.31])['label']=='uncertain'
    assert clip_decision(labels,[.3,.309])['filter_recommendation']=='review'
    assert clip_decision(labels,[.3,.32])['filter_recommendation']=='non_screw_suggestion'
    for scores in ([float('nan'),.3],[.3],[.3,float('inf')]):
        try:clip_decision(labels,scores)
        except ValueError:pass
        else:raise AssertionError('invalid scores accepted')
    if len(sys.argv)>1:
        report=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
        totals={'keep':0,'review':0,'non_screw_suggestion':0};known=[];rows=[]
        for sample in report['samples']:
            predictions={}
            for c in sample['candidates']:
                decision=clip_decision(report['labels'],[c['scores'][label] for label in report['labels']])
                totals[decision['filter_recommendation']]+=1
                predictions[c['candidate_id']]=decision
                rows.append(dict(sample=sample['name'],candidate_id=c['candidate_id'],**decision))
            for region in sample['known_regions']:
                retained=any(predictions[i]['filter_recommendation']!='non_screw_suggestion' for i in region['candidate_ids'])
                assert retained,(sample['name'],region['region'])
                known.append(dict(sample=sample['name'],region=region['region'],retained=retained))
        assert totals==dict(keep=171,review=80,non_screw_suggestion=41),totals
        assert len(known)==8
        result=dict(method='replay of the same exploratory images used to select the margin; not held-out validation',totals=totals,known_regions=known,candidates=rows)
        if len(sys.argv)>2:Path(sys.argv[2]).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(totals,'known regions retained',len(known))
    print('PASS: near ties retained, clear difference distinguished, invalid scores rejected')


if __name__=='__main__':run()
