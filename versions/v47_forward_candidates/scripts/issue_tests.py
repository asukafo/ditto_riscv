"""Check demand-to-I-service handoff and token allocation from actual core VCDs."""
import json
from pathlib import Path
from waveforms import read_vcd,value_at
from window_tests import audit as ownership_audit

def audit(path):
 s=read_vcd(path);w=read_vcd(path,['TOP','rv64_core','request_window','window'])
 r=dict(new_demands=0,same_cycle_service_accepts=0,buffered_on_backpressure=0,simultaneous_demand_response=0,retarget_with_issue=0,queued_service_accepts=0)
 for t,v in s['clk']:
  if not v or value_at(s['reset'],t,True):continue
  p=lambda n:value_at(s[n],t,True)
  q=lambda n:value_at(w[n],t,True)
  new=bool(p('f_valid') and p('f_ready') and not q('found'))
  assert bool(q('new_demand'))==new
  assert bool(q('direct_demand'))==new
  send=bool(p('mw_valid') and p('mw_ready'))
  if new:
   r['new_demands']+=1;slot=q('free_slot')
   assert p('mw_valid')==(q('count')<4 or q('returned'))
   assert p('mw_addr')==p('f_addr') and p('mw_size')==p('f_size') and q('issue_slot')==slot
   assert value_at(w[f'address[{slot}]'],t)==p('f_addr') and value_at(w[f'sizes[{slot}]'],t)==p('f_size')
   assert bool(value_at(w['issued'],t)&(1<<slot))==send
   r['same_cycle_service_accepts']+=send;r['buffered_on_backpressure']+=not send
   r['simultaneous_demand_response']+=bool(send and p('f_rsp_valid') and p('f_rsp_ready'))
   r['retarget_with_issue']+=bool(send and q('retarget'))
  elif send:
   r['queued_service_accepts']+=1;assert q('issue_slot')==(q('match') if q('matched_demand') else q('choose'))
  if send:
   assert value_at(w[f'tokens[{q("rt")}]'],t)==q('issue_slot')
 assert r['same_cycle_service_accepts']>0,path
 return dict(issue=r,ownership=ownership_audit(path))

if __name__=='__main__':
 result={n:audit(f'build/{n}.vcd') for n in ('window_stream','window_redirect','path_calls','path_changing','path_fence')}
 assert sum(x['issue']['simultaneous_demand_response'] for x in result.values())>0
 assert sum(x['issue']['buffered_on_backpressure'] for x in result.values())>0
 Path('build/issue-audit.json').write_text(json.dumps(result,indent=2)+'\n')
 print('DEMAND ISSUE INTERFACE AUDIT PASS: 5 core VCDs; address/size/issued/token/turnover/backpressure/ownership/physical transaction checks')
