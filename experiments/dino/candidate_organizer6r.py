"""Offline candidate organization: difference core -> enclosing target contour.

No DINO scores participate in choosing contours. Every unresolved input keeps
its original identity and is never automatically excluded.
"""
from boundary_shadow6r import analyze


def organize(target, joint):
    groups=joint['groups']['graphcut']
    seeds=[dict(id=g['id'],seed=dict(zip(('x','y','w','h'),g['box']))) for g in groups]
    contours=analyze(target,seeds)
    byid={r['id']:r for r in joint['rows']}
    rows=[];merged={}
    for group,contour in zip(groups,contours['rows']):
        row=dict(group_id=group['id'],members=group['members'],difference_box=group['box'],
                 contour_evidence=contour,status='unknown_outer_boundary',object_box=None,
                 formal_action='unchanged',complete_object_verified=False)
        row['shared_dark_boundary']=any(byid[k]['graphcut']['shared_dark_boundary'] for k in group['members'])
        pairs=contour['stable_pairs']
        if not pairs:rows.append(row);continue
        # Use the outermost supported level-set pair; no confidence or labels
        # select a preferred crop. All alternate hypotheses stay in the record.
        pair=max(pairs,key=lambda p:max(b[2]*b[3] for b in p['boxes']))
        level=pair['levels'][1]
        evidence=next(v for v in contour['levels'] if v['level']==level)
        box=evidence['box']
        row.update(status='enclosing_contour_hypothesis',object_box=box,
                   contour_key=[level,evidence['component']])
        key=tuple(row['contour_key'])
        merged.setdefault(key,dict(box=box,joint_groups=[],members=[],contour_key=list(key),shared_dark_boundary=False))
        merged[key]['shared_dark_boundary'] |= row['shared_dark_boundary']
        merged[key]['joint_groups'].append(group['id']);merged[key]['members'].extend(group['members'])
        rows.append(row)
    output=[]
    for i,g in enumerate(merged.values(),1):
        output.append(dict(g,id=i,members=sorted(set(g['members'])),official_alarm=False))
    return dict(rows=rows,groups=output,mode='offline_candidate_organization',
                unresolved_action='preserve_original_candidate_and_unknown_evidence')
