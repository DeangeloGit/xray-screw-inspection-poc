"""Score every factorial variant using the same reviewed object annotations."""
import json
from pathlib import Path
from collections import Counter
from answered_batch_report import matches
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'workspace/dino-4r-blackblock-20261106';BASE=ROOT/'workspace/dino-4r-correspondence-20261106/final'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
def main():
    plan=read(OUT/'experiment-plan.json');answers=read(OUT/'answers-corrected.json');cs=read(BASE/'cases.json');pred=read(OUT/'ablation-results.json');idx={f'{z["photo"]}-{z["id"]}':z for z in pred}
    truth={c['key']:matches(c['native'],answers.get(c['photo'],{}).get('marks',[]))[0] for c in cs}
    original55={(m['photo'],m['id']) for m in read(BASE/'answer-matches.json') if m['methods']['pilot']};confirmed={('128',11),('135',1)};baseline_kept={c['key'] for c in cs if c['keep']['pilot']}
    def evaluate(kept,photos):
        selected=[c for c in cs if c['photo'] in photos and c['key'] in kept];hits={(c['photo'],i) for c in selected for i in truth[c['key']]};outside=[c['key'] for c in selected if not truth[c['key']]]
        return dict(hits=sorted([list(k) for k in hits]),answer_hits=len(hits),answers=sum(len(answers[k]['marks']) for k in photos if k in answers),kept=len(selected),unmatched=len(outside),unmatched_candidates=outside,big_block_hits=sum((k,10) in hits for k in photos),lost_original55=sorted([list(k) for k in original55 if k[0] in photos and k not in hits]),lost_confirmed=sorted([list(k) for k in confirmed if k[0] in photos and k not in hits]))
    photos=list(answers);base=evaluate(baseline_kept,photos);result={}
    for variant in ('original_old','square_old','original_new','square_new'):
        raw={k for k,z in idx.items() if z['variants'][variant]['keep']}
        # Only test replacing the target-negative classification gate; do not
        # silently bypass existing structure vetoes or paired-reference vetoes.
        eligible={c['key'] for c in cs if c['paired_evidence']['target']['label']!='screw' and not c['rules']}
        rescue=(raw&eligible)|baseline_kept
        entry={}
        for mode,kept in [('replace_all',raw),('rescue_only',rescue)]:
            allmetrics=evaluate(kept,photos);per={p:evaluate(kept,[p]) for p in photos};lost=set(map(tuple,base['hits']))-set(map(tuple,allmetrics['hits']))
            admissible=not lost and not allmetrics['lost_confirmed'] and allmetrics['unmatched']<=base['unmatched'] and all(per[p]['unmatched']<=evaluate(baseline_kept,[p])['unmatched'] for p in photos)
            entry[mode]=dict(all=allmetrics,training=evaluate(kept,plan['training_photos']),heldout=evaluate(kept,plan['heldout_photos']),per_photo=per,passes_safety=admissible,added=sorted(kept-baseline_kept),removed=sorted(baseline_kept-kept),lost_corrected_baseline=sorted([list(k) for k in lost]))
        result[variant]=entry
    report=dict(baseline=base,variants=result,new_examples_training_only=True,scoring_truth_used_only_after_features=True,rescue_route='only prior target-negative candidates without active structure veto; retain existing keeps; do not bypass reference/structure vetoes')
    (OUT/'factorial-evaluation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('BASE',base['answer_hits'],base['unmatched'])
    for k,e in result.items():
        for mode,v in e.items():print(k,mode,'hits',v['all']['answer_hits'],'big',v['all']['big_block_hits'],'heldout_big',v['heldout']['big_block_hits'],'unmatched',v['all']['unmatched'],'safe',v['passes_safety'])
if __name__=='__main__':main()
