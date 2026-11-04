"""Synthetic r3 feature-file integrity checks; no inference or real station export."""
import tempfile
from pathlib import Path
from verify_station_transfer import fixture,t

with tempfile.TemporaryDirectory(prefix='xray-r3-transfer-') as temp:
    base=Path(temp);root=base/'station';root.mkdir();fixture(root)
    model=root/'models/dino-paired';p=model/'manifest.json';m=t.read(p)
    feature=model/'paired-features.npz';feature.write_bytes(b'synthetic-feature-checksum-fixture')
    m.update(feature_strategy='contrast-global-local-half-v1',feature_file=feature.name,feature_sha256=t.sha(feature));t.write(p,m)
    assert t.validate_station(root,work=root)['ok']
    feature.unlink()
    missing=t.validate_station(root,work=root);assert not missing['ok'] and any('r3' in e for e in missing['errors'])
    feature.write_bytes(b'changed')
    changed=t.validate_station(root,work=root);assert not changed['ok'] and any('校驗失敗' in e for e in changed['errors'])
print('PASS: synthetic r3 present/missing/tampered feature checks; no real data exported')
