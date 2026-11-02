"""UI integration: atomic context changes and human-reviewed report previews."""
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory


def checks(root):
    root=root.resolve()
    from app import app
    from runtime_paths import DATA, RESOURCE_ROOT, WORK_ROOT
    from station_settings import read_settings
    shutil.copyfile(RESOURCE_ROOT/'data/ok_0.png',DATA/'ok_0.png')
    shutil.copyfile(RESOURCE_ROOT/'data/ng_5.png',DATA/'001.png')
    source=root/'source';source.mkdir()
    with app.test_client() as client:
        for url in ('/','/engineer','/settings','/engineer?tab=source'):
            response=client.get(url);assert response.status_code==200
            assert '現場複判' in response.text and '工程設定' in response.text
        assert 'data-initial-tab="source"' in client.get('/settings').text
        for name in ('app.css','folder-picker.js','engineer-analysis.js','engineer-shell.js','user.js','settings.js'):
            assert client.get('/static/'+name).status_code==200
        profile=client.post('/api/machines',data={'name':'UI 測試機型','reference':(io.BytesIO((DATA/'ok_0.png').read_bytes()),'正常參考.png')}).json['machine_id']
        preview_image=client.get('/api/machines/'+profile+'/reference?preview=1')
        assert preview_image.status_code==200 and preview_image.content_type=='image/png'
        import cv2, numpy as np
        assert max(cv2.imdecode(np.frombuffer(preview_image.data,np.uint8),cv2.IMREAD_GRAYSCALE).shape)<=160
        before=read_settings()
        bad=client.post('/api/inspection/context',json={'id':profile,'source':str(WORK_ROOT),'enabled':True})
        assert bad.status_code==400 and read_settings()==before,'invalid source must not partially switch machine'
        assert client.post('/api/inspection/context',json={'id':'missing','source':str(source),'enabled':True}).status_code==400
        saved=client.post('/api/inspection/context',json={'id':profile,'source':'','enabled':False})
        assert saved.status_code==200 and read_settings()['selected_machine']==profile
        listing=client.get('/api/samples').json
        assert listing['reference']=='正常參考.png'
        item=next(p for p in listing['items'] if not p['is_reference'])
        ids=[item['id']]
        assert client.post('/api/reports/screws/preview',json={'sample_ids':ids}).json['unresolved_count']==1
        result=client.post('/api/analyze',data={'sample':item['id']}).json
        for candidate in result['candidates']:
            assert client.post('/api/review/'+result['name'],json={'id':candidate['id'],'label':'screw' if candidate['id']==result['candidates'][0]['id'] else 'normal'}).status_code==200
        summarized=client.get('/api/samples/'+item['id']+'/result').json
        assert summarized['image_review']['decision']=='screw' and summarized['image_review']['by']=='human_positions'
        before_reports=set((WORK_ROOT/'reports').glob('*'))
        preview=client.post('/api/reports/screws/preview',json={'sample_ids':ids})
        assert preview.status_code==200 and preview.json['screw_rows']==1
        assert preview.json['rows'][0]['sn']=='' and preview.json['machine']=='UI 測試機型'
        assert set((WORK_ROOT/'reports').glob('*'))==before_reports,'preview must not export files'
        report=client.post('/api/reports/screws',json={'sample_ids':ids})
        assert report.status_code==200 and report.headers['X-Screw-Rows']=='1'
        client.post('/api/review/'+result['name'],json={'id':result['candidates'][0]['id'],'label':'uncertain'})
        assert client.post('/api/reports/screws',json={'sample_ids':ids,'preview_token':preview.json['preview_token']}).status_code==409,'an edit after preview must invalidate export'
        client.post('/api/review/'+result['name'],json={'id':result['candidates'][0]['id'],'label':'normal'})
        assert client.get('/api/samples/'+item['id']+'/result').json['image_review']['decision']=='no_screw_seen'
        empty=client.post('/api/reports/screws/preview',json={'sample_ids':ids})
        assert empty.status_code==200 and empty.json['rows']==[]
        # A no-candidate image still needs one explicit human decision.
        image=cv2.imdecode(np.frombuffer((DATA/'ok_0.png').read_bytes(),np.uint8),cv2.IMREAD_UNCHANGED)
        rotated=cv2.imencode('.png',np.rot90(image).copy())[1].tobytes()
        zero=client.post('/api/analyze',data={'image':(io.BytesIO(rotated),'normal-rotated.png')}).json
        assert zero['proposal_count']==0 and not zero.get('image_review')
        zero_ids=[zero['sample_id']]
        assert client.post('/api/reports/screws/preview',json={'sample_ids':zero_ids}).json['unresolved_count']==1
        assert client.post('/api/image-review/'+zero['name'],json={'decision':'no_screw_seen'}).status_code==200
        assert client.post('/api/reports/screws/preview',json={'sample_ids':zero_ids}).status_code==200
        # Legacy fully labeled positions can be summarized without inventing a review time.
        from library import save_result
        legacy=client.get('/api/samples/'+item['id']+'/result').json
        legacy.pop('image_review',None);legacy.pop('candidate_reviews_updated_at',None)
        save_result(legacy)
        legacy_result=client.get('/api/samples/'+item['id']+'/result').json
        assert legacy_result['image_review']['decision']=='no_screw_seen' and legacy_result['image_review']['at']==''
        token=listing['machine']['id']+':'+listing['machine']['reference_sha256']
        client.post('/api/inspection/context',json={'id':profile,'source':str(source),'enabled':False})
        assert client.post('/api/reports/screws/preview',json={'sample_ids':ids},headers={'X-Inspection-Machine':token,'X-Inspection-Source':'local'}).status_code==400
    print('PASS: redesigned routes/assets, atomic context validation, reference names, guarded read-only preview, CSV, position-only completion, uncertain export guard, zero-candidate manual decision, legacy summary and stale-source protection')


if __name__=='__main__':
    if len(sys.argv)>1:checks(Path(sys.argv[1]))
    else:
        with TemporaryDirectory() as directory:
            root=Path(directory)
            config=root/'station.json'
            config.write_text(json.dumps(dict(workspace=str(root/'workspace'),model_root=str(root/'models'))))
            subprocess.run([sys.executable,__file__,str(root)],check=True,env=dict(os.environ,XRAY_CONFIG=str(config),XRAY_WORKSPACE=str(root/'workspace')))
