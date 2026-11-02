"""Isolated machine/reference switching and manual-review separation regression."""
import io
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory


def checks(root):
    import cv2
    import numpy as np
    from app import app
    from runtime_paths import DATA, RESOURCE_ROOT
    from library import latest_results, analyze_sample, select_sample, save_result
    from machine_profiles import selected_profile
    shutil.copyfile(RESOURCE_ROOT/'data/ok_0.png', DATA/'ok_0.png')
    shutil.copyfile(RESOURCE_ROOT/'data/ng_5.png', DATA/'target.png')
    image=(DATA/'ok_0.png').read_bytes()
    with app.test_client() as client:
        def create(name, content=image, profile_id=''):
            return client.post('/api/machines',data=dict(name=name,id=profile_id,reference=(io.BytesIO(content),'正常.png')))
        def select(machine):
            response=client.post('/api/machines/select',json={'id':machine})
            assert response.status_code==200,response.json
            return response.json['machine']
        a=create('機型 A'); assert a.status_code==200,a.json
        aid=a.json['machine_id']
        b=create('機型 B'); assert b.status_code==200
        bid=b.json['machine_id']
        assert create('機型 A').status_code==400
        assert create('壞圖',b'not an image').status_code==400
        assert client.post('/api/machines/select',json={}).status_code==400
        assert client.post('/api/machines/select',json={'id':'unknown'}).status_code==400
        assert client.get('/api/machines/'+aid+'/reference').data==image
        profile=select(aid)
        token=profile['id']+':'+profile['reference_sha256']
        target=select_sample('target.png')
        first=analyze_sample(target)
        first['human_reviews']={str(c['id']):'normal' for c in first['candidates']}
        first['image_review']={'decision':'no_screw_seen','at':'2026-11-02T00:00:00+00:00'}
        save_result(first)
        assert client.get('/api/samples/'+target['id']+'/result').json['image_review']['decision']=='no_screw_seen'
        first['image_review']['decision']='screw'
        save_result(first)
        report=client.post('/api/reports/screws',json={'sample_ids':[target['id']]})
        assert report.status_code==200
        rows=list(csv.DictReader(io.StringIO(report.data.decode('utf-8-sig'))))
        assert rows and rows[0]['檢測機型']=='機型 A' and rows[0]['SN']==''
        assert rows[0]['參考圖 SHA-256']==profile['reference_sha256']
        select(bid)
        assert client.get('/api/samples/'+target['id']+'/result').status_code==404
        assert client.post('/api/reports/screws',json={'sample_ids':[target['id']]}).headers['X-Unresolved-Rows']=='1'
        assert client.post('/api/analyze',data={'sample':target['id']},headers={'X-Inspection-Machine':token}).status_code==400
        assert client.post('/api/image-review/'+first['name'],json={'decision':'screw'}).status_code==409
        second=analyze_sample(target)
        assert second['name']!=first['name'] and not second.get('image_review')
        select(aid)
        assert latest_results()[target['sha256']]['name']==first['name']
        assert latest_results()[target['sha256']]['image_review']['decision']=='screw'
        # Real changed image bytes invalidate prior review; old snapshot remains intact.
        changed=cv2.imdecode(np.frombuffer(image,np.uint8),cv2.IMREAD_UNCHANGED)
        changed[0:10,0:10]=0
        content=cv2.imencode('.png',changed)[1].tobytes()
        assert create('機型 A',content,aid).status_code==200
        assert client.get('/api/samples/'+target['id']+'/result').status_code==404
        assert Path(first['machine']['reference']).read_bytes()==image
        assert client.post('/api/reports/screws',json={'sample_ids':[target['id']]}).headers['X-Unresolved-Rows']=='1'
        assert len(client.get('/api/machines').json['items'])==3
        assert 'inspection-machine' in client.get('/').text
        assert 'machine-form' in client.get('/engineer').text
    subprocess.run([sys.executable,'-c',f"from machine_profiles import selected_profile, profiles; assert selected_profile()['id']=={aid!r}; assert len(profiles())==3"],check=True,env=os.environ)
    print('PASS: machine UI/API, validation, immutable references, context cache/review/report isolation, stale page guard and restart persistence')


if __name__=='__main__':
    if len(sys.argv)>1:
        checks(Path(sys.argv[1]))
    else:
        with TemporaryDirectory() as directory:
            root=Path(directory)
            config=root/'station.json'
            config.write_text(json.dumps(dict(workspace=str(root/'workspace'),model_root=str(root/'models'))))
            subprocess.run([sys.executable,__file__,str(root)],check=True,env=dict(os.environ,XRAY_CONFIG=str(config),XRAY_WORKSPACE=str(root/'workspace')))
