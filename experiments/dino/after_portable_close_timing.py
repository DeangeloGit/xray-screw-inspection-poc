"""Repeat the same eight-run protocol after the authorized idle portable stop."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.dino import paired_answer_timing as experiment
experiment.OUT=ROOT/'workspace/dino-after-portable-close-20261104'
if __name__=='__main__':experiment.main()
