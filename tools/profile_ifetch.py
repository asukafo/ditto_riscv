"""Count pre-edge front-end waits and demand-return forwarding opportunities."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'versions/v18_btb_window/scripts'))
from waveforms import read_vcd,value_at

def profile(path):
 s=read_vcd(path);w=read_vcd(path,['TOP','rv64_core','request_window','window'])
 r=dict(new_demand_accepts=0,new_demand_same_cycle_service_accepts=0,new_demand_buffered=0,cycles=0,x_starved=0,f_waiting=0,f_request_blocked=0,window_demand_waiting=0,demand_return_edges=0,demand_return_waits_one_more_cycle=0,forwarded_demand_returns=0)
 for t,v in s['clk']:
  if not v or value_at(s['reset'],t,True):continue
  p=lambda n:value_at(s[n],t,True)
  q=lambda n:value_at(w[n],t,True)
  r['cycles']+=1
  r['x_starved']+=int(p('state')==0 and not p('fe_valid') and not p('serialize_pending') and not p('irq_stop') and not p('halted'))
  r['f_waiting']+=p('fe_waiting')
  r['f_request_blocked']+=int(p('f_valid') and not p('f_ready'))
  if not w:continue
  if q('new_demand'):
   r['new_demand_accepts']+=1
   direct=bool(p('mw_valid') and p('mw_ready') and p('mw_addr')==p('f_addr') and p('mw_size')==p('f_size'))
   r['new_demand_same_cycle_service_accepts']+=direct;r['new_demand_buffered']+=not direct
  demand=q('demand');waiting=q('active') and q('valid')&(1<<demand) and not q('done')&(1<<demand) and not q('poison')&(1<<demand)
  r['window_demand_waiting']+=bool(waiting)
  arrival=waiting and q('count') and p('mw_rsp_valid') and p('mw_rsp_ready') and q('owner')==demand and not p('fetch_redirect')
  if arrival:
   r['demand_return_edges']+=1
   r['demand_return_waits_one_more_cycle']+=not p('f_rsp_valid')
   r['forwarded_demand_returns']+=bool(p('f_rsp_valid') and p('f_rsp_ready'))
 return r
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('vcd');a=p.parse_args();print(json.dumps(profile(a.vcd),indent=2))
