"""Audit ordered cached responses and refill ownership while accepting younger hits."""
import argparse,csv,json,shutil,subprocess
from collections import deque
from pathlib import Path
from native_test_support import NativeSuite
from reference import verify_files
from window_tests import audit as ownership_audit
from waveforms import read_vcd,value_at

def audit(path,enabled):
 s=read_vcd(path);c=read_vcd(path,['TOP','rv64_core','memory_system','split','icache']);pending=deque();held=None
 r=dict(cache_requests=0,cache_responses=0,background_hits=0,fill_hits=0,hit_while_refill_response_pending=0,held_response_cycles=0,hit_on_final_refill=0,peak_cache_requests=0)
 for t,v in s['clk']:
  if not v or value_at(s['reset'],t,True):continue
  p=lambda n:value_at(s[n],t,True)
  q=lambda n:value_at(c[n],t,True)
  packet=(q('u_rsp_data'),q('u_rsp_error'))
  if held is not None:assert q('u_rsp_valid') and packet==held;r['held_response_cycles']+=1
  if q('u_rsp_valid') and q('u_rsp_ready'):
   assert pending;expected=pending.popleft();r['cache_responses']+=1
   if expected is not None:assert packet==(expected,0)
  bg=q('state') in (2,3)
  eligible=bool(enabled and bg and q('early') and q('beat') and not q('poisoned') and q('hit') and (not q('response_available') or q('u_rsp_ready')) and q('u_valid'))
  fill=bool(p('icache_fill_forward_enabled') and bg and q('early') and q('beat') and not q('poisoned') and q('cacheable') and q('first_fits') and not q('invalidate') and q('u_addr')>>3==q('address')>>3 and (not q('response_available') or q('u_rsp_ready')) and q('u_valid'))
  assert bool(q('fill_hit_event'))==fill
  assert bool(q('refill_hit_event'))==eligible
  if q('u_valid') and q('u_ready'):
   r['cache_requests']+=1;expected=None
   if q('hit'):
    addr=q('u_addr');line=q(f'lines[{(addr>>4)&15}]');expected=(line>>((addr&15)*8))&((1<<(8*(1<<q('u_size'))))-1)
   if fill:expected=(q('fill_low')>>((q('u_addr')&7)*8))&((1<<(8*(1<<q('u_size'))))-1)
   pending.append(expected)
   if bg:
    assert (eligible or fill) and q('early') and q('beat')
    if not fill:assert ((q('u_addr')>>4)&15)!=((q('address')>>4)&15)
    assert value_at(c['address'],t)==q('address') and value_at(c['size'],t)==q('size')
    assert value_at(c['response'],t)==expected and value_at(c['response_available'],t) and not value_at(c['response_error'],t)
    r['background_hits']+=not fill;r['fill_hits']+=fill;r['hit_on_final_refill']+=bool(q('state')==3 and q('d_rsp_valid'))
    r['hit_while_refill_response_pending']+=bool(q('state')==3)
  assert len(pending)<=1;r['peak_cache_requests']=max(r['peak_cache_requests'],len(pending))
  held=packet if q('u_rsp_valid') and not q('u_rsp_ready') else None
 if not enabled:assert r['background_hits']==0
 return dict(cache=r,ownership=ownership_audit(path))

def main():
 p=argparse.ArgumentParser();p.add_argument('--cross',default='riscv64-elf-');a=p.parse_args();suite=NativeSuite(a.cross)
 cases={'stream':('window_stream',128),'c':('priority_c',1488),'calls':('path_calls',64),'fence':('path_fence',43),'changing':('path_changing',48)}
 rows=[];audits={}
 for name,(source,expected) in cases.items():
  stem='under_'+name;shutil.copyfile(f'build/{source}.bin',f'build/{stem}.bin')
  suite.run(stem,signature=expected,causes=[],timings=[(1,0),(5,0),(1,3),(5,7),(20,3)])
  for latency,gap in [(1,0),(5,0),(5,3)]:
   pair=[]
   for mode in ['full','nounder']:
    trace=f'build/under-{name}-{mode}-l{latency}-g{gap}.trace.jsonl'
    stats=json.loads(subprocess.check_output([f'build/{mode}_obj/Vrv64_core',f'build/{stem}.bin',str(latency),'-',str(gap),trace],text=True))
    assert stats['result']==expected and verify_files(f'build/{stem}.bin',trace)==stats['instret'];pair.append(stats)
   on,off=pair;assert on['instret']==off['instret'] and off['icache_refill_hits_enabled']==off['icache_refill_hits']==0
   rows.append(dict(program=name,latency=latency,gap=gap,on_cycles=on['cycles'],off_cycles=off['cycles'],on_requests=on['requests'],off_requests=off['requests'],refill_hits=on['icache_refill_hits']))
  audits[name]={}
  for mode,enabled in [('full',True),('nounder',False)]:
   wave=f'build/under-{name}-{mode}.vcd';trace=f'build/under-wave-{name}-{mode}.trace.jsonl'
   subprocess.run([f'build/{mode}_obj/Vrv64_core',f'build/{stem}.bin','5',wave,'3',trace],check=True,capture_output=True,text=True)
   verify_files(f'build/{stem}.bin',trace);audits[name][mode]=audit(wave,enabled)
 assert sum(x['full']['cache']['background_hits'] for x in audits.values())>0
 assert sum(x['full']['cache']['hit_while_refill_response_pending'] for x in audits.values())>0
 with Path('build/under-ablation.csv').open('w',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
 Path('build/under-audit.json').write_text(json.dumps(audits,indent=2)+'\n');Path('build/under-native-stats.json').write_text(json.dumps(suite.stats,indent=2)+'\n')
 print(f'HIT UNDER REFILL INTEGRATION PASS: {suite.runs} runs, {suite.commits} commits, {suite.traps} traps; 30 on/off runs; 10 cache response/refill/ownership VCD audits')
if __name__=='__main__':main()
