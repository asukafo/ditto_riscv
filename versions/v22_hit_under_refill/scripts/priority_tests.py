"""Native scheduling audit: matched unsent demands must outrank other prefetches."""
import argparse,csv,json,shutil,subprocess
from pathlib import Path
from native_test_support import NativeSuite
from reference import verify_files
from window_tests import audit as ownership_audit
from waveforms import read_vcd,value_at

def audit(path,enabled):
 s=read_vcd(path);w=read_vcd(path,['TOP','rv64_core','request_window','window'])
 r=dict(eligible=0,service_ready=0,sent_match=0,sent_other=0,old_selector_differs=0,priority_override_sent=0,blocked=0,existing_issued_or_done=0)
 for t,v in s['clk']:
  if not v or value_at(s['reset'],t,True):continue
  p=lambda n:value_at(s[n],t,True)
  q=lambda n:value_at(w[n],t,True)
  take=bool(p('f_valid') and p('f_ready'));match=q('match')
  eligible=bool(take and q('found') and not q('issued')&(1<<match) and not q('done')&(1<<match))
  assert bool(q('matched_demand'))==(eligible and enabled)
  send=bool(p('mw_valid') and p('mw_ready'))
  if take and q('found') and not eligible:r['existing_issued_or_done']+=1
  if eligible:
   r['eligible']+=1;r['service_ready']+=p('mw_ready');r['blocked']+=not p('mw_ready')
   same=bool(send and p('mw_addr')==p('f_addr') and p('mw_size')==p('f_size'))
   r['sent_match']+=same;r['sent_other']+=bool(send and not same)
   differs=bool(q('choose_found') and q('choose')!=match);r['old_selector_differs']+=differs
   if enabled:
    assert q('issue_slot')==match and p('mw_valid')
    assert p('mw_addr')==p('f_addr') and p('mw_size')==p('f_size')
    assert bool(value_at(w['issued'],t)&(1<<match))==send
    assert not p('mw_ready') or same
    r['priority_override_sent']+=bool(differs and send)
   elif send:assert q('issue_slot')==q('choose')
 return dict(priority=r,ownership=ownership_audit(path))

def main():
 p=argparse.ArgumentParser();p.add_argument('--cross',default='riscv64-elf-');a=p.parse_args();suite=NativeSuite(a.cross)
 cases={'redirect':('window_redirect',16),'skip':('path_skip',16),'fence':('path_fence',43),'changing':('path_changing',48),'c':('c_demo',1488)}
 rows=[];audits={}
 for name,(source,expected) in cases.items():
  stem='priority_'+name;shutil.copyfile(f'build/{source}.bin',f'build/{stem}.bin')
  suite.run(stem,signature=expected,causes=[],timings=[(1,0),(5,0),(1,3),(5,7),(20,3)])
  for latency,gap in [(1,0),(5,0),(5,3)]:
   pair=[]
   for mode in ['full','nopriority']:
    trace=f'build/priority-{name}-{mode}-l{latency}-g{gap}.trace.jsonl'
    stats=json.loads(subprocess.check_output([f'build/{mode}_obj/Vrv64_core',f'build/{stem}.bin',str(latency),'-',str(gap),trace],text=True))
    assert stats['result']==expected and verify_files(f'build/{stem}.bin',trace)==stats['instret'];pair.append(stats)
   on,off=pair;assert on['instret']==off['instret'] and off['demand_priority_enabled']==0
   rows.append(dict(program=name,latency=latency,gap=gap,on_cycles=on['cycles'],off_cycles=off['cycles'],on_requests=on['requests'],off_requests=off['requests'],on_control_misses=on['control_misses'],off_control_misses=off['control_misses']))
  audits[name]={}
  for mode,enabled in [('full',True),('nopriority',False)]:
   wave=f'build/priority-{name}-{mode}.vcd';trace=f'build/priority-wave-{name}-{mode}.trace.jsonl'
   subprocess.run([f'build/{mode}_obj/Vrv64_core',f'build/{stem}.bin','5',wave,'3',trace],check=True,capture_output=True,text=True)
   verify_files(f'build/{stem}.bin',trace);audits[name][mode]=audit(wave,enabled)
 assert sum(x['full']['priority']['priority_override_sent'] for x in audits.values())>0
 assert all(x['full']['priority']['sent_other']==0 for x in audits.values())
 assert sum(x['nopriority']['priority']['sent_other'] for x in audits.values())>0
 with Path('build/priority-ablation.csv').open('w',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
 Path('build/priority-audit.json').write_text(json.dumps(audits,indent=2)+'\n');Path('build/priority-native-stats.json').write_text(json.dumps(suite.stats,indent=2)+'\n')
 print(f'DEMAND PRIORITY INTEGRATION PASS: {suite.runs} runs, {suite.commits} commits, {suite.traps} traps; 30 on/off runs; 10 VCD priority/token/ownership audits')
if __name__=='__main__':main()
