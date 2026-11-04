"""Start the preserved local workspace on its established port."""
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['XRAY_WORKSPACE']=str(ROOT/'workspace/windows-check')
import launch
launch.URL='http://127.0.0.1:18766'
bind=launch.bind_server
launch.bind_server=lambda app:bind(app,ports=(18766,))
if __name__=='__main__':launch.main()
