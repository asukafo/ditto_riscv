"""Partition blocked I requests using pre-edge MMU/cache/physical-arbiter state."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'versions/v18_btb_window/scripts'))
from waveforms import read_vcd,value_at

def profile(path):
 s=read_vcd(path);m=read_vcd(path,['TOP','rv64_core','memory_system','split','fmmu']);c=read_vcd(path,['TOP','rv64_core','memory_system','split','icache']);a=read_vcd(path,['TOP','rv64_core','memory_system','split','physical_arbiter'])
 iv='mw_valid' if 'mw_valid' in s else 'f_valid';ir='mw_ready' if 'mw_ready' in s else 'f_ready'
 r=dict(offered_blocked=0,mmu_walk=0,mmu_access_request=0,mmu_fault_response=0,cache_refill_request=0,cache_refill_response=0,cache_response_blocked=0,cache_bypass=0,other=0,background_blocked_hit=0,background_refill_cycles=0,refill_waiting_arbiter=0,refill_waiting_memory_response=0,refill_blocked_by_data_owner=0,refill_blocked_by_instruction_owner=0,refill_lost_arbitration=0)
 for t,v in s['clk']:
  if not v or value_at(s['reset'],t,True):continue
  p=lambda n:value_at(s[n],t,True)
  q=lambda d,n:value_at(d[n],t,True)
  cs=q(c,'state');ms=q(m,'state');background=cs in (2,3) and q(c,'early') and q(c,'beat')
  r['background_refill_cycles']+=bool(background)
  wait_arb=bool(cs==2 and not q(c,'d_ready'))
  r['refill_waiting_arbiter']+=wait_arb
  if wait_arb:
   if q(a,'state')==0:r['refill_lost_arbitration']+=1
   elif q(a,'owner')&1:r['refill_blocked_by_data_owner']+=1
   else:r['refill_blocked_by_instruction_owner']+=1
  r['refill_waiting_memory_response']+=bool(cs==3 and not q(c,'d_rsp_valid'))
  if not(p(iv) and not p(ir)):continue
  r['offered_blocked']+=1
  if ms in (2,3):r['mmu_walk']+=1
  elif ms==4:r['mmu_access_request']+=1
  elif ms==6:r['mmu_fault_response']+=1
  elif cs==2:r['cache_refill_request']+=1
  elif cs==3:r['cache_refill_response']+=1
  elif cs==4:r['cache_response_blocked']+=1
  elif cs==1:r['cache_bypass']+=1
  else:r['other']+=1
  r['background_blocked_hit']+=bool(background and q(c,'u_valid') and not q(c,'u_ready') and q(c,'hit') and not q(c,'invalidate') and (not q(c,'response_available') or q(c,'u_rsp_ready')))
 assert r['offered_blocked']==sum(r[k] for k in ['mmu_walk','mmu_access_request','mmu_fault_response','cache_refill_request','cache_refill_response','cache_response_blocked','cache_bypass','other'])
 assert r['refill_waiting_arbiter']==sum(r[k] for k in ['refill_blocked_by_data_owner','refill_blocked_by_instruction_owner','refill_lost_arbitration'])
 return r
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('vcd');a=p.parse_args();print(json.dumps(profile(a.vcd),indent=2))
