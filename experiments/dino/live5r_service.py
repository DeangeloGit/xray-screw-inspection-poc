"""5r UI and isolated batch reports, retaining the verified 4r classifier."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ['XRAY_4R_HOME'] = os.environ.get('XRAY_5R_HOME', str(ROOT/'workspace/5r-live'))
os.environ['XRAY_5R_BATCH'] = '1'
os.environ.setdefault('XRAY_4R_PROVIDER', 'cpu')
import live4r_service  # Registers 5r before starting the shared, unchanged classifier.
