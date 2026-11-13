"""Run qualified 5r local review in its own home; no fallback for missing data."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault('XRAY_5R_HOME', str(ROOT / 'workspace/5r-local-review-20261113'))
os.environ.setdefault('XRAY_5R_PORT', '18767')
os.environ['XRAY_5R_LOCAL_REVIEW'] = '1'
import live5r_service
