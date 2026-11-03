"""The appearance refinement cannot override screw winners or use reference images."""
import numpy as np
from model_adapters import clip_decision,refine_cable_shape
v=np.zeros(512,np.float32);v[0]=1
m={'cable_shape':{'embedding':v.tolist()}}
for scores in ([.31,.3],[.3,.32]):
    d=clip_decision(['screw','cable'],scores)
    assert refine_cable_shape(m,v,d,scores)==d
d=clip_decision(['screw','cable'],[.3,.305])
assert refine_cable_shape(m,v,d,[.3,.305])['label']=='cable'
v[0]=.305
assert refine_cable_shape(m,v,d,[.3,.305])['label']=='uncertain'
assert refine_cable_shape({},v,d,[.3,.305])==d
print('PASS: screw winners unchanged, existing decisions unchanged, original margin enforced, optional model compatibility')
