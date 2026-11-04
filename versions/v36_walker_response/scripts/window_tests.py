"""Interface-level outstanding/ownership audit, including repeated redirects."""
import argparse,json,csv,subprocess
from collections import deque
from pathlib import Path
from native_test_support import NativeSuite,words
from waveforms import read_vcd,value_at

def audit(path):
 s=read_vcd(path);w=read_vcd(path,['TOP','rv64_core','request_window','window']);pending=deque();peak=sent=dropped=flushes=0;first=None;physical=physical_peak=0
 for cycle,(t,v) in enumerate([(t,v) for t,v in s['clk'] if v==1 and not value_at(s['reset'],t,True)],1):
  p=lambda n:value_at(s[n],t,True)
  assert p('ifetch_window_pending')==len(pending)
  clear=p('fetch_redirect') or value_at(w['retarget'],t,True)
  if clear:
   for entry in pending:entry['poison']=True
   flushes+=1
  if p('mw_rsp_valid') and p('mw_rsp_ready'):
   assert pending;entry=pending.popleft();owner=value_at(w['owner'],t,True)
   assert owner==entry['slot'] and value_at(w[f'address[{owner}]'],t,True)==entry['addr']
   assert bool(p('ifetch_window_drop_event'))==entry['poison']
   if entry['poison']:dropped+=1
   else:
    assert value_at(w[f'payload[{owner}]'],t)==p('mw_rsp_data')
    assert value_at(w[f'causes[{owner}]'],t)==p('mw_rsp_cause')
  if p('mw_valid') and p('mw_ready'):
   slot=value_at(w['issue_slot'],t,True);assert all(e['slot']!=slot for e in pending)
   pending.append(dict(slot=slot,addr=p('mw_addr'),size=p('mw_size'),poison=False));sent+=1
  assert len(pending)<=4
  if len(pending)>peak:peak=len(pending);first=cycle if peak==2 else first
  assert value_at(s['ifetch_window_pending'],t)==len(pending)
  if p('rsp_valid') and p('rsp_ready'):physical-=1
  if p('req_valid') and p('req_ready'):physical+=1
  assert 0<=physical<=1
  physical_peak=max(physical_peak,physical)
 assert peak>=2,(path,peak)
 return dict(accepted_requests=sent,max_accepted_not_returned=peak,poisoned_completions=dropped,redirect_or_retarget_cycles=flushes,first_double_outstanding_cycle=first,max_external_physical_transactions=physical_peak)

def main():
 p=argparse.ArgumentParser();p.add_argument('--cross',default='riscv64-elf-');a=p.parse_args();suite=NativeSuite(a.cross)
 finish='sd a0,512(zero)\nSIM_EXIT\n'
 cases={
 'stream':('''li s0,16
 li a0,0
1:
 .rept 8
 addi a0,a0,1
 .endr
 addi s0,s0,-1
 bnez s0,1b
 '''+finish,128),
 'redirect':('''li s0,16
 li a0,0
1: addi a0,a0,1
 jal zero,target
 li t0,99
 sd t0,528(zero)
 .word 0
 target:
 addi s0,s0,-1
 bnez s0,1b
 '''+finish,16),
 'fence':('''la s0,func
 jalr ra,0(s0)
 mv s1,a0
 li t0,0x02a00513
 sw t0,0(s0)
 fence.i
 jalr ra,0(s0)
 add a0,a0,s1
 '''+finish+'''func: li a0,1
 nop
 ret
 ''',43)}
 results={}
 for name,(body,signature) in cases.items():
  n='window_'+name;suite.compile(n,body);runs=suite.run(n,signature=signature,causes=[],timings=[(1,0),(5,0),(1,3),(5,7),(20,3)])
  for (_,ram),stats in zip(runs,suite.stats[-5:]):
   assert stats['ifetch_window_peak']>=2 and words(ram,528,1)==[0]
  wave=f'build/{n}.vcd';subprocess.run([suite.simulator,f'build/{n}.bin','5',wave,'3'],check=True,capture_output=True,text=True);results[name]=audit(wave)
 assert results['redirect']['poisoned_completions']>0 and results['fence']['poisoned_completions']>0
 Path('build/window-audit.json').write_text(json.dumps(results,indent=2)+'\n')
 Path('build/window-native-stats.json').write_text(json.dumps(suite.stats,indent=2)+'\n')
 print(f'WINDOW INTEGRATION PASS: {suite.runs} runs, {suite.commits} commits, {suite.traps} traps; interface/slot audit {results}')
if __name__=='__main__':main()
