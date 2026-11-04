"""Run the existing isolated folder timing experiment with process-local patches."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
mode=sys.argv[1]
assert mode in ('base','combined')
original=ROOT/'experiments/dino/folder_pipeline_timing.py'
source=original.read_text(encoding='utf-8')
needle=" for name in ['read','register','refine','proposals','legacy_proposals','write_image']:"
assert source.count(needle)==1
source=source.replace(needle,f" from experiments.dino.three_speed_pilot import ThreeSpeed\n three_speed=ThreeSpeed(detector,reuse,{mode!r},workers=2,inner_threads=16).install()\n"+needle)
source=source.replace(" if args.cpu_reuse!='off':mode+='-cpu-reuse-'+args.cpu_reuse", " if args.cpu_reuse!='off':mode+='-cpu-reuse-'+args.cpu_reuse\n mode+='-three-speed-"+mode+"'")
sys.argv=[str(original),'--prepare-once','--cpu-reuse','warm']
exec(compile(source,str(original),'exec'),dict(__name__='__main__',__file__=str(original)))
