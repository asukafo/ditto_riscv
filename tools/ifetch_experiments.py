"""Cycle-only hit-pipeline/window experiments with independent commit/RAM checks."""
import argparse,csv,hashlib,json,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
from benchmark import PROGRAMS,TIMINGS,write_csv
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'versions/v1_multicycle/scripts'))
from reference import verify_files

def main():
 p=argparse.ArgumentParser();p.add_argument('--cycles-only',action='store_true');p.add_argument('--versions',nargs='+',default=['v16_ifetch_pipeline','v18_btb_window','v19_window_forward']);p.add_argument('--run-id',default=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));a=p.parse_args()
 assert a.run_id.replace('_','').replace('-','').isalnum() and len(set(a.versions))==len(a.versions)
 out=ROOT/'results/comparisons'/a.run_id;out.mkdir(parents=True,exist_ok=False);rows=[];images={};baselines={}
 for version in a.versions:
  assert version in ('v15_fetch_queue','v16_ifetch_pipeline','v17_fetch_window','v18_btb_window','v19_window_forward')
  folder=ROOT/'versions'/version;result=folder/'results'/a.run_id;result.mkdir(parents=True,exist_ok=False)
  off='nopipe' if version=='v16_ifetch_pipeline' else 'nowindow' if version=='v17_fetch_window' else 'nopath' if version=='v18_btb_window' else 'noforward' if version=='v19_window_forward' else None
  targets=['build/full_obj/Vrv64_core']+([f'build/{off}_obj/Vrv64_core'] if off else [])+[f'build/{n}.bin' for n in PROGRAMS if not (ROOT/'benchmarks'/f'{n}.S').exists()]
  with (result/'build.log').open('w') as log:subprocess.run(['make',*targets],cwd=folder,stdout=log,stderr=subprocess.STDOUT,check=True)
  for n in PROGRAMS:
   source=ROOT/'benchmarks'/f'{n}.S'
   if source.exists():
    subprocess.run(['riscv64-elf-gcc','-march=rv64imac_zicsr_zifencei','-mabi=lp64','-nostdlib','-nostartfiles','-Wl,-Ttext=0,-e,_start,--no-relax','-o',f'build/{n}.elf',str(source)],cwd=folder,check=True)
    subprocess.run(['riscv64-elf-objcopy','-O','binary','-j','.text',f'build/{n}.elf',f'build/{n}.bin'],cwd=folder,check=True)
  manifest={'version':version,'run_id':a.run_id,'measurement':'cycles_only','rtl_sha256':{q.name:hashlib.sha256(q.read_bytes()).hexdigest() for q in sorted((folder/'rtl').glob('*.sv'))},'version_metadata':json.loads((folder/'version.json').read_text()),'images':{},'tools':{'verilator':subprocess.check_output(['verilator','--version'],text=True).strip()}}
  own=[];ablation=[]
  for name,expected in PROGRAMS.items():
   image=folder/'build'/f'{name}.bin';digest=hashlib.sha256(image.read_bytes()).hexdigest();assert name not in images or images[name]==digest;images[name]=digest;manifest['images'][name]=digest
   for latency,gap in TIMINGS:
    stats=[]
    for mode in (['full',off] if off else ['full']):
     trace=folder/'build'/f'{a.run_id}-{name}-{mode}-l{latency}-g{gap}.trace.jsonl'
     s=json.loads(subprocess.check_output([str(folder/'build'/f'{mode}_obj/Vrv64_core'),str(image),str(latency),'-',str(gap),str(trace)],cwd=folder,text=True))
     assert s['result']==expected and verify_files(image,trace)==s['instret'];stats.append(s)
    s=stats[0];key=(name,latency,gap)
    row=dict(version=version,program=name,latency=latency,gap=gap,instret=s['instret'],cycles=s['cycles'],requests=s['requests'],control_misses=s['control_misses'],window_peak=s.get('ifetch_window_peak',''),window_hits=s.get('ifetch_window_hits',''),window_drops=s.get('ifetch_window_drops',''),frontend_starved_cycles=s['frontend_starved_cycles'],window_forward_enabled=s.get('window_forward_enabled',''),path_queries=s.get('prefetch_path_queries',''),path_redirects=s.get('prefetch_path_redirects',''),path_rejects=s.get('prefetch_path_rejects',''),path_page_blocks=s.get('prefetch_path_page_blocks',''))
    own.append(row);rows.append(row);baselines[version,key]=s
    if off:
     if off=='noforward':assert stats[1]['window_forward_enabled']==0
     if off=='nopath':assert stats[1]['prefetch_path_enabled']==stats[1]['prefetch_path_queries']==stats[1]['prefetch_path_redirects']==0
     parent='v15_fetch_queue' if off=='nopipe' else 'v16_ifetch_pipeline' if off=='nowindow' else 'v17_fetch_window' if off=='nopath' else 'v18_btb_window';b=baselines.get((parent,key))
     if b:assert all(stats[1][k]==b[k] for k in ('cycles','requests','control_misses','instret')),(version,key,stats[1],b)
     ablation.append(dict(program=name,latency=latency,gap=gap,enabled_cycles=s['cycles'],disabled_cycles=stats[1]['cycles'],disabled_matches_parent=bool(b)))
  write_csv(result/'performance.csv',own)
  if ablation:write_csv(result/'feature-ablation.csv',ablation)
  (result/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(version,len(own),'checked cases',flush=True)
 write_csv(out/'comparison.csv',rows);(out/'README.md').write_text('Cycle-only experiment. Byte-identical images; every committed instruction and full RAM checked against the independent model. Feature-off configurations checked against selected parent versions.\n');print(out,flush=True)
if __name__=='__main__':main()
