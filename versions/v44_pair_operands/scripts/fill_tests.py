"""Ablation and physical-half ownership audit for refill-data forwarding."""
import csv,json,subprocess
from pathlib import Path
from reference import verify_files
from under_tests import audit

def main():
 rows=[];audits={}
 for name in ['stream','c','calls','fence','changing']:
  image=f'build/under_{name}.bin'
  for l,g in [(1,0),(5,0),(5,3)]:
   pair=[]
   for mode in ['full','nofill']:
    trace=f'build/fill-{name}-{mode}-l{l}-g{g}.trace.jsonl';s=json.loads(subprocess.check_output([f'build/{mode}_obj/Vrv64_core',image,str(l),'-',str(g),trace],text=True));assert verify_files(image,trace)==s['instret'];pair.append(s)
   on,off=pair;assert on['result']==off['result'] and on['instret']==off['instret'] and off['icache_fill_forward_enabled']==off['icache_fill_hits']==0
   rows.append(dict(program=name,latency=l,gap=g,on_cycles=on['cycles'],off_cycles=off['cycles'],fill_hits=on['icache_fill_hits']))
  audits[name]={}
  for mode in ['full','nofill']:
   wave=f'build/fill-{name}-{mode}.vcd';trace=f'build/fill-wave-{name}-{mode}.trace.jsonl';subprocess.run([f'build/{mode}_obj/Vrv64_core',image,'5',wave,'3',trace],check=True,capture_output=True);verify_files(image,trace);audits[name][mode]=audit(wave,True)
 assert sum(x['full']['cache']['fill_hits'] for x in audits.values())>0
 assert all(x['nofill']['cache']['fill_hits']==0 for x in audits.values())
 with Path('build/fill-ablation.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
 Path('build/fill-audit.json').write_text(json.dumps(audits,indent=2)+'\n');print('FILL FORWARD INTEGRATION PASS: 30 on/off runs; 10 response/half-address/order/ownership VCD audits')
if __name__=='__main__':main()
