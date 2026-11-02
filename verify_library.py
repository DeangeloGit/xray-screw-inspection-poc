"""Library discovery, caching and review workflow checks; real review files preserved."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json, time, shutil, uuid
import numpy as np
import cv2
from app import app
import library
from detector import ROOT


def run():
    with TemporaryDirectory() as directory:
        data=Path(directory)
        with patch.object(library,'DATA',data):
            cv2.imwrite(str(data/'a.png'),np.zeros((128,128),np.uint16))
            assert len(library.catalog())==1
            shutil.copyfile(data/'a.png',data/'duplicate.png')
            assert len(library.catalog())==1 and len(library.catalog()[0]['aliases'])==2
            (data/'new').mkdir()
            cv2.imwrite(str(data/'new/b.tiff'),np.ones((128,128),np.uint16))
            assert len(library.catalog())==2
    with app.test_client() as client:
        user=client.get('/').text
        engineer=client.get('/engineer').text
        assert 'static/user.js' in user
        assert '差分門檻' not in user and 'benchmark' not in user
        assert '差分門檻' in engineer and '工程設定' in engineer
        assert client.get('/static/user.js').status_code==200
        listing=client.get('/api/samples').json
        assert listing['file_count']>=23 and listing['unique_count']>=21
        target_count=sum(not i['is_reference'] for i in listing['items'])
        assert target_count>=20
        five=next(i for i in listing['items'] if i['filename']=='5.png')
        assert {'5.png','ng_5.png'}.issubset(set(five['aliases']))
        first=client.post('/api/analyze',data={'sample':five['id']})
        second=client.post('/api/analyze',data={'sample':'ng_5'})
        assert first.status_code==second.status_code==200
        assert first.json['name']==second.json['name']
        assert client.post('/api/analyze',data={'sample':'../../app.py'}).status_code==400
        assert client.get('/api/samples/invalid/result').status_code==404
        # Isolated copy of a real result: do not change operator reviews on source photographs.
        name=uuid.uuid4().hex[:12]
        result=first.json
        result['name']=name
        result.pop('human_reviews',None);result.pop('image_review',None)
        (ROOT/'outputs'/name).mkdir()
        library.save_result(result)
        assert client.post(f'/api/image-review/{name}',json={'decision':'no_screw_seen'}).status_code==400
        for c in result['candidates']:
            label='uncertain' if c['id']==1 else 'normal'
            assert client.post(f'/api/review/{name}',json={'id':c['id'],'label':label}).status_code==200
        assert client.post(f'/api/image-review/{name}',json={'decision':'no_screw_seen'}).status_code==400
        assert client.post(f'/api/image-review/{name}',json={'decision':'uncertain'}).status_code==200
        assert client.get(f'/outputs/{name}/result.json').json['image_review']['decision']=='uncertain'
        assert client.post(f'/api/review/{name}',json={'id':1,'label':'normal'}).status_code==200
        assert client.get(f'/outputs/{name}/result.json').json['image_review']['decision']=='no_screw_seen'
        assert client.post(f'/api/image-review/{name}',json={'decision':'no_screw_seen'}).status_code==200
        assert client.post(f'/api/image-review/{name}',json={'decision':'invalid'}).status_code==400
        job=client.post('/api/batch').json
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            state=client.get('/api/batch/'+job['id']).json
            if state['state']=='done':break
            time.sleep(.1)
        assert state['state']=='done' and state['completed']==target_count and not state['errors'],state
        assert client.get('/api/batch/invalid').status_code==404
        shutil.rmtree(ROOT/'outputs'/name)
    print('PASS: automatic discovery + deduplication, mode separation, cached aliases, all 20 batch items, review persistence and completion guards')

if __name__=='__main__':run()
