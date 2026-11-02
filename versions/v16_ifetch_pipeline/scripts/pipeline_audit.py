"""Prove same-cycle response/request handover while retaining a single outstanding read."""
import json,subprocess
from pathlib import Path
from waveforms import read_vcd,value_at
from reference import verify_files
subprocess.run(['build/full_obj/Vrv64_core','build/independent.bin','1','build/hit-pipeline.vcd','0','build/hit-pipeline.trace.jsonl'],check=True,capture_output=True,text=True)
s=read_vcd('build/hit-pipeline.vcd');pending=peak=exchanges=0
for t,v in s['clk']:
 if v!=1 or value_at(s['reset'],t,True):continue
 p=lambda n:value_at(s[n],t,True)
 accept=p('f_valid') and p('f_ready');response=p('f_rsp_valid') and p('f_rsp_ready')
 exchanges+=accept and response;pending+=int(accept)-int(response);peak=max(peak,pending);assert 0<=pending<=1
assert exchanges>0 and peak==1
assert verify_files('build/independent.bin','build/hit-pipeline.trace.jsonl')>0
result=dict(simultaneous_response_and_next_accept=exchanges,max_outstanding=peak)
Path('build/pipeline-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(result)
