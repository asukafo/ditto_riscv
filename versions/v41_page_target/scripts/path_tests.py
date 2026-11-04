"""BTB-guided prefetch: independent predictor replay, metadata and ownership checks."""
import argparse,json,csv,subprocess
from pathlib import Path
from native_test_support import NativeSuite,words
from reference import verify_files
from full_reference import decompress
from window_tests import audit as ownership_audit
from waveforms import read_vcd,value_at
MASK=(1<<64)-1

def control(insn,pc,next_pc=0):
 op=insn&127;f=(insn>>12)&7
 if op==0x63 and f in (0,1,4,5,6,7):
  off=((insn>>31)<<12)|(((insn>>7)&1)<<11)|(((insn>>25)&63)<<5)|(((insn>>8)&15)<<1)
  if off&4096:off-=8192
  return 1,(pc+off)&MASK
 if op==0x6f:
  off=((insn>>31)<<20)|(((insn>>12)&255)<<12)|(((insn>>20)&1)<<11)|(((insn>>21)&1023)<<1)
  if off&1048576:off-=2097152
  return 2,(pc+off)&MASK
 if op==0x67 and f==0:
  ret=(insn>>7)&31==0 and (insn>>15)&31 in (1,5) and insn>>20==0
  return (3 if ret else 4),next_pc
 return 0,0

def audit(path):
 s=read_vcd(path);w=read_vcd(path,['TOP','rv64_core','request_window','window'])
 table=[None]*32;counters=[1]*32;valid=[False]*32;history=0;forecasts=[None]*4;queries=redirects=rejects=skip_allocations=skip_advances=0;examples=[]
 for cycle,(t,v) in enumerate([(t,v) for t,v in s['clk'] if v==1 and not value_at(s['reset'],t,True)],1):
  p=lambda n:value_at(s[n],t,True)
  f=lambda n:value_at(w[n],t,True)
  pc=f('path_pc');wide=bool(p('wide_fetch_enabled'))
  if 'alloc_pc' in w:
   spec=f('spec_pc')
   expected=spec
   if p('CURSOR_SKIP') and p('prefetch_path_enabled') and f('spec_in_page'):
    hops=[]
    for _ in range(2):
     matches=[k for k in range(4)
              if (f('valid') & ~f('poison')) & (1<<k)
              and f(f'address[{k}]')==expected
              and f(f'sizes[{k}]')==(3 if wide and not expected&4 else 2)]
     if matches:
      expected=forecasts[matches[-1]]['next']
     hops.append(expected)
    if any(addr>>12!=f('spec_page') for addr in hops):expected=spec
   assert f('alloc_pc')==expected
   if f('advance'):
    skip_advances+=expected!=spec
   if f('allocate'):
    assert value_at(w[f"address[{f('free_slot')}]"],t)==expected
    skip_allocations+=expected!=spec
  def lookup(addr):
   entry=table[(addr>>1)&31];hit=entry is not None and entry['pc']==addr and not addr&1
   k=entry['kind'] if hit else 0;target=entry['target'] if hit else 0;length=entry['bytes'] if hit else 0
   idx=((addr>>1)&31)^history;dest=p('ras_target') if k==3 and p('ras_valid') else target
   taken=k!=1 or (counters[idx]>=2 if valid[idx] else entry['backward'])
   eligible=hit and not addr&3 and length in (2,4)
   hint=bool(eligible and (not taken or (not dest&3 and dest>>12==addr>>12)))
   block=bool(eligible and taken and dest>>12!=addr>>12)
   return dict(hint=hint,block=block,next=dest if hint and taken else (addr+4)&MASK,kind=k,target=target,bytes=length)
  low=lookup(pc);high=lookup(pc+4);upper=wide and not pc&4 and not(low['hint'] and low['next']!=(pc+4)&MASK) and high['hint'] and high['next']!=(pc+8)&MASK
  selected=high if upper else low;hint=bool(upper or (low['hint'] and low['next']!=(pc+4)&MASK)) if wide else low['hint']
  block=low['block'] or (wide and not pc&4 and high['block']);sequential=(pc+(8 if wide and not pc&4 else 4))&MASK
  use=hint and bool(f('path_eligible'));nxt=selected['next'] if use else sequential
  kind=selected['kind'];target=selected['target'];length=selected['bytes']
  if p('prefetch_path_query_event'):
   assert f('chosen_next')==nxt and bool(f('use_hint'))==use,(cycle,hex(pc),selected,history)
   assert bool(p('prefetch_path_page_block_event'))==block
   assert bool(p('prefetch_path_redirect_event'))==(nxt!=sequential)
   queries+=1;redirects+=nxt!=sequential
   if nxt!=sequential and len(examples)<8:examples.append(dict(cycle=cycle,pc=pc,target=nxt,kind=kind))
  # Every owner carries the forecast made at its allocation, never a later lookup.
  if f('returned') and not f('poison')&(1<<f('owner')) and not p('fetch_redirect') and not f('retarget'):
   owner=f('owner');old=forecasts[owner]
   if old and old['used']:
    raw=p('mw_rsp_data')>>(32 if old['upper'] else 0);size=2 if raw&3!=3 else 4
    try:insn=decompress(raw&65535) if size==2 else raw&0xffffffff;k,direct=control(insn,f(f'address[{owner}]')+(4 if old['upper'] else 0))
    except ValueError:k=0;direct=0
    ok=not p('mw_rsp_error') and k==old['kind'] and size==old['bytes'] and (k not in (1,2) or direct==old['target'])
    assert bool(p('prefetch_path_reject_event'))==(not ok)
    rejects+=not ok
  if f('advance') and f('exists'):
   old=forecasts[f('existing_slot')];assert old is not None
   assert value_at(w['spec_offset'],t)==(old['next'] & 0xfff)
   assert bool(value_at(w['spec_in_page'],t))==(old['next']>>12==f('spec_page'))
  if f('new_demand') or f('allocate'):
   slot=f('free_slot');forecasts[slot]=dict(used=use,kind=kind,bytes=length,target=target,next=nxt,upper=upper)
   assert value_at(w[f'forecast_offset[{slot}]'],t)==(nxt & 0xfff)
   assert bool(value_at(w['forecast_in_page'],t)&(1<<slot))==(nxt>>12==pc>>12)
   assert value_at(w['spec_offset'],t)==(nxt & 0xfff)
   assert bool(value_at(w['spec_in_page'],t))==(nxt>>12==pc>>12)
   assert bool(value_at(w['forecast_used'],t)&(1<<slot))==use
  if p('trap_enter') or (p('retire') and p('wb_serial')):
   table=[None]*32;counters=[1]*32;valid=[False]*32;history=0
  else:
   if p('bht_train_event'):
    i=p('wb_predicted_index');tk=p('wb_branch_taken');counters[i]=(2 if tk else 1) if not valid[i] else min(3,counters[i]+1) if tk else max(0,counters[i]-1)
    valid[i]=True;history=((history<<1)|tk)&15
   if p('btb_train_event'):
    insn=p('wb_insn');pc=p('wb_pc');k,target=control(insn,pc,p('wb_next'));assert k
    table[(pc>>1)&31]=dict(pc=pc,kind=k,target=target,bytes=p('wb_bytes'),backward=bool(insn>>31))
 assert queries>0 and redirects>0
 return dict(queries=queries,path_redirects=redirects,rejected_returned_metadata=rejects,skip_allocations=skip_allocations,skip_advances=skip_advances,examples=examples)

def main():
 p=argparse.ArgumentParser();p.add_argument('--cross',default='riscv64-elf-');a=p.parse_args();suite=NativeSuite(a.cross)
 finish='sd a0,512(zero)\nSIM_EXIT\n'
 cases={
 'calls':('''li s0,16
 li a0,0
 la s1,func
1: jalr ra,0(s1)
 addi s0,s0,-1
 bnez s0,1b
 '''+finish+'''func:
 .rept 4
 addi a0,a0,1
 .endr
 ret
 ''',64),
 'alternating':('''li s0,64
 li a0,0
1: andi t0,s0,1
 bnez t0,2f
 addi a0,a0,1
2: addi a0,a0,1
 addi s0,s0,-1
 bnez s0,1b
 '''+finish,96),
 'changing':('''li s0,32
 li a0,0
1: andi t0,s0,1
 la s1,f1
 beqz t0,2f
 la s1,f2
2: jalr ra,0(s1)
 addi s0,s0,-1
 bnez s0,1b
 '''+finish+'''f1: addi a0,a0,1
 ret
 f2: addi a0,a0,2
 ret
 ''',48),
 'fence':('''la s0,func
 li s1,8
1: jalr ra,0(s0)
 addi s1,s1,-1
 bnez s1,1b
 mv s2,a0
 li t0,0x02a00513
 sw t0,0(s0)
 fence.i
 jalr ra,0(s0)
 add a0,a0,s2
 '''+finish+'''func: li a0,1
 nop
 ret
 ''',43),
 'skip':('''li s0,16
 li a0,0
1: addi a0,a0,1
 jal zero,target
 li t0,99
 sd t0,528(zero)
 .word 0
 target: addi s0,s0,-1
 bnez s0,1b
 '''+finish,16)}
 for name,(body,sig) in cases.items():
  suite.compile('path_'+name,body);runs=suite.run('path_'+name,signature=sig,causes=[],timings=[(1,0),(5,0),(1,3),(5,7),(20,3)])
  for (_,ram),stats in zip(runs,suite.stats[-5:]):assert words(ram,528,1)==[0] and stats['prefetch_path_redirects']>0
 rows=[]
 for name in cases:
  for latency,gap in [(1,0),(5,0),(5,3)]:
   pair=[]
   for mode,sim in [('path',suite.simulator),('linear','build/nopath_obj/Vrv64_core')]:
    trace=f'build/path-{name}-{mode}-l{latency}-g{gap}.trace.jsonl'
    stats=json.loads(subprocess.check_output([sim,f'build/path_{name}.bin',str(latency),'-',str(gap),trace],text=True));assert verify_files(f'build/path_{name}.bin',trace)==stats['instret'];pair.append(stats)
   on,off=pair;assert on['result']==off['result'] and on['instret']==off['instret']
   assert off['prefetch_path_enabled']==off['prefetch_path_redirects']==off['prefetch_path_queries']==0
   rows.append(dict(program=name,latency=latency,gap=gap,path_cycles=on['cycles'],linear_cycles=off['cycles'],path_requests=on['requests'],linear_requests=off['requests'],path_drops=on['ifetch_window_drops'],linear_drops=off['ifetch_window_drops']))
 with Path('build/path-ablation.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
 audits={}
 for name in ('calls','alternating','changing','fence','skip'):
  wave=f'build/path_{name}.vcd';subprocess.run([suite.simulator,f'build/path_{name}.bin','5',wave,'3'],check=True,capture_output=True,text=True)
  audits[name]=dict(predictor=audit(wave),ownership=ownership_audit(wave))
 Path('build/path-audit.json').write_text(json.dumps(audits,indent=2)+'\n');Path('build/path-native-stats.json').write_text(json.dumps(suite.stats,indent=2)+'\n')
 print(f'PATH INTEGRATION PASS: {suite.runs} runs, {suite.commits} commits, {suite.traps} traps; 30 on/off runs; independent predictor/metadata/slot replay')
if __name__=='__main__':main()
