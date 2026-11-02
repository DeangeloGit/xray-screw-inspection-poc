"""Native coordinate and real-image checks for reflected acquisition files."""
import cv2
import numpy as np
from detector import register,read,source_points,structure_mask,correlation
from pathlib import Path


def run():
    raw=np.zeros((300,400),np.uint8);raw[111,222]=1
    for mirrored in (False,True):
        for k in range(4):
            oriented=np.rot90(np.fliplr(raw) if mirrored else raw,k)
            yy,xx=np.where(oriented)
            reg=dict(matrix=np.eye(2,3),target_scale=1.,rotation=k,mirrored=mirrored)
            native=source_points([[xx[0],yy[0]]],reg,np.zeros((400,400,2),np.float32),raw.shape)
            assert np.allclose(native,[[222,111]]),(mirrored,k,native)
    root=Path('workspace/windows-check/data')
    ref=read(root/'ok_0.png');ref=cv2.resize(ref,None,fx=1536/max(ref.shape),fy=1536/max(ref.shape))
    normal=register(ref,read(root/'ok_0.png'))
    assert not normal['mirrored']
    reflected=register(ref,np.fliplr(read(root/'ok_0.png')).copy())
    assert reflected['mirrored']
    assert correlation(ref,reflected['aligned'],structure_mask(ref))>.98
    print('PASS: native coordinates for all eight orientations, ordinary normal preserved, reflected normal restored')


if __name__=='__main__':run()
