"""Count pre-edge front-end waits and demand-return forwarding opportunities."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'versions/v18_btb_window/scripts'))
from waveforms import read_vcd,value_at

def profile(path):
 s=read_vcd(path);w=read_vcd(path,['TOP','rv64_core','request_window','window'])
 r=dict(active_unsent_service_busy=0,active_unsent_not_offered=0,active_unsent_sent=0,active_unsent_other_selected=0,matched_unissued_accepts=0,matched_unissued_service_ready=0,matched_unissued_sent=0,matched_unissued_other_selected=0,cycles_with_active_unsent_demand=0,new_demand_accepts=0,new_demand_same_cycle_service_accepts=0,new_demand_buffered=0,cycles=0,x_starved=0,f_waiting=0,f_request_blocked=0,window_demand_waiting=0,demand_return_edges=0,demand_return_waits_one_more_cycle=0,forwarded_demand_returns=0)
 for t,v in s['clk']:
  if not v or value_at(s['reset'],t,True):continue
  p=lambda n:value_at(s[n],t,True)
  q=lambda n:value_at(w[n],t,True)
  r['cycles']+=1
  r['x_starved']+=int(p('state')==0 and not p('fe_valid') and not p('serialize_pending') and not p('irq_stop') and not p('halted'))
  r['f_waiting']+=p('fe_waiting')
  r['f_request_blocked']+=int(p('f_valid') and not p('f_ready'))
  if not w:continue
  if q('take') and q('found') and not q('issued')&(1<<q('match')):
   r['matched_unissued_accepts']+=1
   r['matched_unissued_service_ready']+=p('mw_ready')
   sent=bool(p('mw_valid') and p('mw_ready') and p('mw_addr')==p('f_addr') and p('mw_size')==p('f_size'))
   r['matched_unissued_sent']+=sent
   r['matched_unissued_other_selected']+=bool(p('mw_valid') and p('mw_ready') and not sent)
  active_unsent=bool(q('active') and q('valid')&(1<<q('demand')) and not q('issued')&(1<<q('demand')) and not q('poison')&(1<<q('demand')))
  r['cycles_with_active_unsent_demand']+=active_unsent
  if active_unsent:
   if not p('mw_ready'):r['active_unsent_service_busy']+=1
   elif not p('mw_valid'):r['active_unsent_not_offered']+=1
   elif p('mw_addr')==q(f'address[{q("demand")}]') and p('mw_size')==q(f'sizes[{q("demand")}]'):r['active_unsent_sent']+=1
   else:r['active_unsent_other_selected']+=1
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
 assert sum(r[k] for k in ('active_unsent_service_busy','active_unsent_not_offered','active_unsent_sent','active_unsent_other_selected'))==r['cycles_with_active_unsent_demand']
 return r
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('vcd');a=p.parse_args();print(json.dumps(profile(a.vcd),indent=2))
