"""Isolated integration of per-machine preview/apply and production analysis."""
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from tempfile import TemporaryDirectory


def checks(fixtures):
    from app import app
    from runtime_paths import DATA, OUTPUTS
    from station_settings import read_settings, update_settings, detection_threshold
    from machine_profiles import selected_profile
    from library import analyze_file, latest_results
    for name in ('ok_0.png','ng_5.png','ng_9.png'):
        shutil.copyfile(fixtures/name, DATA/name)
    update_settings(detection_threshold=.13, custom_preserved='keep')
    with app.test_client() as client:
        def create(name):
            response=client.post('/api/machines',data={'name':name,'reference':(io.BytesIO((DATA/'ok_0.png').read_bytes()),'normal.png')})
            assert response.status_code==200, response.json
            return response.json['machine_id']
        a,b=create('Machine A'),create('Machine B')
        def preview(machine, threshold):
            profile=selected_profile(machine)
            return client.post('/api/machines/'+machine+'/tuning/preview',data={'image':(io.BytesIO((DATA/'ng_5.png').read_bytes()),'abnormal.png'),'threshold':str(threshold),'reference_sha256':profile['reference_sha256']})
        assert client.post('/api/settings/detection',json={'threshold':.12}).status_code==409
        before_settings=read_settings()
        before_files=set(DATA.rglob('*'))
        response=preview(a,.12)
        assert response.status_code==200,response.json
        first=response.json
        assert read_settings()==before_settings and set(DATA.rglob('*'))==before_files
        assert not list(OUTPUTS.glob('*/result.json'))
        assert client.get(first['assets']['aligned']).status_code==200
        import cv2, numpy as np
        aligned=cv2.imdecode(np.frombuffer(client.get(first['assets']['aligned']).data,np.uint8),cv2.IMREAD_GRAYSCALE)
        overlay=cv2.imdecode(np.frombuffer(client.get(first['assets']['aligned_overlay']).data,np.uint8),cv2.IMREAD_COLOR)
        assert overlay.shape[:2]==aligned.shape
        # Background pixels must remain exactly the aligned image, not a rotation of the input.
        unchanged=np.all(overlay==aligned[:,:,None],axis=2)
        assert unchanged.mean()>.95
        details=first['result']; base=details['tuning_asset_base']
        assert len(details['local_alignment'])==9
        for filename in ('source.png','difference.png','result.json'):
            assert client.get(base+'/'+filename).status_code==200
        candidate=details['candidates'][0]
        assert client.get(base+'/crop_'+str(candidate['id'])+'.png').status_code==200
        assert client.post(base+'/review',json={'id':candidate['id'],'label':'screw'}).status_code==200
        assert client.get(base+'/result.json').json['human_reviews'][str(candidate['id'])]=='screw'
        assert client.get(base+'/../preview.json').status_code==404
        assert client.get('/api/machines/'+a+'/tuning/catalog').json['machine']['id']==a
        assert client.get(first['assets']['aligned'].replace('/'+a+'/', '/'+b+'/')).status_code==404
        assert client.post('/api/machines/'+b+'/tuning/apply',json={'preview_id':first['preview_id']}).status_code==409
        assert client.post('/api/machines/'+a+'/tuning/apply',json={'preview_id':first['preview_id']}).status_code==200
        assert detection_threshold(a)==.12 and detection_threshold(b)==.13
        assert read_settings().get('selected_machine','default')=='default'
        assert read_settings()['custom_preserved']=='keep'
        assert client.post('/api/machines/'+a+'/tuning/apply',json={'preview_id':first['preview_id']}).status_code==409
        assert preview(a,.99).status_code==400
        assert client.post('/api/machines/'+a+'/tuning/apply',json={'threshold':.10}).status_code==400
        client.post('/api/machines/select',json={'id':a})
        item=next(i for i in client.get('/api/samples').json['items'] if i['filename']=='ng_5.png')
        result=client.post('/api/analyze',data={'sample':item['id']})
        assert result.status_code==200 and result.json['threshold']==.12,result.json
        assert analyze_file(DATA/'ng_9.png','incoming.png')['threshold']==.12
        upload=client.post('/api/analyze',data={'image':(io.BytesIO((DATA/'ng_9.png').read_bytes()),'new.png')})
        assert upload.status_code==200 and upload.json['threshold']==.12
        job=client.post('/api/batch').json
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            state=client.get('/api/batch/'+job['id']).json
            if state['state']!='running': break
            time.sleep(.1)
        assert state['state']=='done' and not state['errors'],state
        assert all(r['threshold']==.12 for r in latest_results().values())
        client.post('/api/machines/select',json={'id':b})
        result=client.post('/api/analyze',data={'sample':item['id']})
        assert result.status_code==200 and result.json['threshold']==.13
        subprocess.run([sys.executable,'-c',f"from station_settings import detection_threshold; assert detection_threshold({a!r})==.12; assert detection_threshold({b!r})==.13"],check=True,env=os.environ)
        response=preview(a,.11); assert response.status_code==200,response.json
        token=response.json['preview_id']
        # Reference content changed after preview must invalidate application.
        response=client.post('/api/machines',data={'id':a,'name':'Machine A','reference':(io.BytesIO((DATA/'ng_9.png').read_bytes()),'replacement.png')})
        assert response.status_code==200
        assert client.post('/api/machines/'+a+'/tuning/apply',json={'preview_id':token}).status_code==409
        assert detection_threshold(a)==.12
        html=client.get('/engineer/machines/'+a+'/tuning').text
        assert '套用至 Machine A' in html and 'tuning-image' in html and 'id="sample"' not in html
        for feature in ('id="viewer"','id="high-cards"','id="low-cards"','id="alignment"','id="audit"','id="folder-summary"','id="benchmark"','id="download"'):
            assert feature in html,feature
        assert 'data-engineer-tab="tuning"' not in client.get('/engineer').text
    print('PASS: isolated previews, explicit apply, machine isolation, preserved settings/source, invalid/stale apply protection, user/upload/acquisition/batch thresholds, fresh-process persistence and simplified page')


if __name__=='__main__':
    if len(sys.argv)>2 and sys.argv[1]=='--child': checks(Path(sys.argv[2]))
    else:
        fixtures=Path(sys.argv[1] if len(sys.argv)>1 else 'data').resolve()
        with TemporaryDirectory() as directory:
            root=Path(directory); config=root/'station.json'
            config.write_text(json.dumps({'workspace':str(root/'workspace'),'model_root':str(root/'models')}))
            subprocess.run([sys.executable,__file__,'--child',str(fixtures)],check=True,env=dict(os.environ,XRAY_CONFIG=str(config),XRAY_WORKSPACE=str(root/'workspace'),PYTHONUTF8='1'))
