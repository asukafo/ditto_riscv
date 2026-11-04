"""Replay demand-return selection and backpressure directly at the RTL interfaces."""
import json
from pathlib import Path
from waveforms import read_vcd,value_at
from window_tests import audit as ownership_audit

def audit(path):
 s=read_vcd(path);w=read_vcd(path,['TOP','rv64_core','request_window','window'])
 counts=dict(return_candidates=0,forwarded_and_consumed=0,forwarded_but_stalled=0,simultaneous_successor=0,flush_with_forward=0,held_response_cycles=0)
 held=None
 for t,v in s['clk']:
  if not v or value_at(s['reset'],t,True):continue
  p=lambda n:value_at(s[n],t,True)
  q=lambda n:value_at(w[n],t,True)
  demand=q('demand');mask=1<<demand
  candidate=bool(q('active') and q('valid')&mask and not q('done')&mask and not q('poison')&mask and q('returned') and q('owner')==demand)
  assert bool(q('forward_return'))==candidate
  packet=(p('f_rsp_data'),p('f_rsp_cause'),p('f_rsp_error'))
  if held is not None and not p('fetch_redirect') and not q('cancelled'):
   assert p('f_rsp_valid') and packet==held
   counts['held_response_cycles']+=1
  if candidate:
   assert p('f_rsp_valid') and not q('cancelled')
   assert packet==(p('mw_rsp_data'),p('mw_rsp_cause'),p('mw_rsp_error'))
   counts['return_candidates']+=1
   counts['forwarded_and_consumed']+=bool(p('f_rsp_ready'))
   counts['forwarded_but_stalled']+=not p('f_rsp_ready')
   counts['simultaneous_successor']+=bool(p('f_rsp_ready') and p('f_valid') and p('f_ready'))
   counts['flush_with_forward']+=p('fetch_redirect')
  held=packet if p('f_rsp_valid') and not p('f_rsp_ready') and not p('fetch_redirect') else None
 assert counts['forwarded_and_consumed']>0,path
 return dict(forwarding=counts,ownership=ownership_audit(path))

if __name__=='__main__':
 result={name:audit(f'build/{name}.vcd') for name in ('window_stream','window_redirect','path_calls','path_changing','path_fence')}
 assert sum(x['forwarding']['simultaneous_successor'] for x in result.values())>0
 Path('build/forward-audit.json').write_text(json.dumps(result,indent=2)+'\n')
 print('FORWARD INTERFACE AUDIT PASS: 5 actual core VCDs; owner/data/cause/error/held response/successor/physical transaction checks')
