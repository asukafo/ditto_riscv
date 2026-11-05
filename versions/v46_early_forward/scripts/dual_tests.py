"""Conservative two-lane ALU execution, precise retirement and packet-order checks."""
import argparse,json,subprocess,copy
from pathlib import Path
from collections import deque
from native_test_support import NativeSuite,words
from reference import verify_files,verify
from waveforms import read_vcd,value_at

def pair_integer(insn):
 opcode=insn&127
 funct3=(insn>>12)&7
 funct7=insn>>25
 if opcode in (0x37,0x17):return True
 if opcode==0x13:
  if funct3==1:return insn>>26==0
  if funct3==5:return insn>>26 in (0,16)
  return True
 if opcode==0x33:return funct7==0 or (funct7==32 and funct3 in (0,5))
 if opcode==0x1b:return funct3==0 or (funct3==1 and funct7==0) or (funct3==5 and funct7 in (0,32))
 if opcode==0x3b:return funct3 in (0,1,5) and (funct7==0 or (funct7==32 and funct3 in (0,5)))
 return False

def audit(path):
 s=read_vcd(path);q=deque();pairs=commits=raw_reject=waw_reject=0
 wide=bool(s.get("wide_fetch_enabled",[(0,0)])[-1][1])
 if wide:
  from wide_audit import audit as wide_audit
  wide_audit(path)
 for t,v in s['clk']:
  if not v or value_at(s['reset'],t,True):continue
  p=lambda n:value_at(s[n],t,True)
  if not wide:
   assert p('issue_pair_occupancy')==len(q)
   uv=p('queued_valid');packet=p('queued_packet');available=len(q)+bool(uv)
   assert bool(p('fe_valid'))==bool(not p('fetch_redirect') and available)
   if p('fe_valid'):assert p('fe_packet')==(q[0] if q else packet)
   if p('second_valid'):assert p('second_packet')==(q[1] if len(q)==2 else packet)
  if p('ex_finish'):assert p('state')!=p('EMPTY')
  # A live second lane can only be replaced when its current X completes.
  if p('issue_fire') and p('xp_valid'):assert p('ex_finish')
  if p('xp_valid') and not p('ex_finish'):
   for operand in ('xp_a','xp_b'):assert value_at(s[operand],t)==p(operand)
  if p('issue_fire') or p('pair_fire'):
   def expected_operand(r,rf):
    if r==0:return 0
    if p('ex_finish') and p('xp_valid') and p('xp_rd')==r:return p('xp_result')
    if p('ex_finish') and p('ex_rd_wen') and p('ex_rd')==r:return p('ex_result')
    if p('retire') and p('wb_pair') and p('wp_rd')==r:return p('wp_result')
    if p('wb_write_enable') and p('wb_rd')==r:return p('wb_writeback')
    return p(rf)
   if p('issue_fire'):
    assert value_at(s['a'],t)==expected_operand(p('issue_rs1'),'register_a')
    assert value_at(s['b'],t)==expected_operand(p('issue_rs2'),'register_b')
   if p('pair_fire'):
    assert value_at(s['xp_a'],t)==expected_operand(p('p2_rs1'),'register_c')
    assert value_at(s['xp_b'],t)==expected_operand(p('p2_rs2'),'register_d')
  if p('state')!=p('EMPTY') and not p('ex_finish'):
   for operand in ('a','b'):assert value_at(s[operand],t)==p(operand)
  if p('pair_fire'):
   assert p('issue_fire') and p('second_valid') and pair_integer(p('fe_insn')) and pair_integer(p('p2_insn'))
   rd=p('fe_insn')>>7&31;i=p('p2_insn');assert not(rd and ((i&127 not in (0x37,0x17) and rd==(i>>15&31)) or (i&127 in (0x33,0x3b) and rd==(i>>20&31))))
   assert not(rd and rd==(i>>7&31));assert p('p2_pc')==p('fe_pc')+p('fe_bytes');pairs+=1
  if p('issue_fire') and p('second_valid'):
   raw_reject+=bool(p('pair_raw'));waw_reject+=bool(p('pair_waw'))
  if not wide:
   if p('fetch_redirect'):q.clear()
   else:
    if uv and p('queued_ready'):q.append(packet)
    for _ in range((2 if p('pair_fire') else 1) if p('issue_fire') else 0):assert q;q.popleft()
   assert len(q)<=2 and value_at(s['issue_pair_occupancy'],t)==len(q)
  if value_at(s['commit2_valid'],t):
   assert value_at(s['commit_valid'],t);assert value_at(s['commit_next_pc'],t)==value_at(s['commit2_pc'],t);commits+=1
 return dict(pair_issues=pairs,dual_retire_cycles=commits,raw_guard_events=raw_reject,waw_guard_events=waw_reject)

def main():
 p=argparse.ArgumentParser();p.add_argument('--cross',default='riscv64-elf-');a=p.parse_args();suite=NativeSuite(a.cross)
 finish='sd a0,512(zero)\nSIM_EXIT\n';stall='li a4,1000\nli a5,7\ndiv zero,a4,a5\n'
 cases={
 'burst':(stall+'li a0,0\nli a1,0\n'+'.rept 8\naddi a0,a0,1\naddi a1,a1,2\n.endr\nadd a0,a0,a1\n'+finish,24,False,[]),
 'zero':(stall+'addi zero,zero,7\naddi t0,zero,5\nadd a0,zero,t0\n'+finish,5,False,[]),
 'raw':('li a0,0\n'+stall+'.rept 32\naddi a0,a0,1\n.endr\n'+finish,32,False,[]),
 'waw':(stall+'.rept 8\naddi a0,zero,1\naddi a0,zero,2\n.endr\n'+finish,2,False,[]),
 'war':('li t0,7\n'+stall+'add a0,t0,zero\naddi t0,zero,13\nadd a0,a0,t0\n'+finish,20,False,[]),
 'forward':(stall+'addi t0,zero,7\naddi t1,zero,11\nadd t2,t1,t0\naddi t3,zero,13\nadd a0,t2,t3\n'+finish,31,False,[]),
 'csr':('csrw minstret,zero\nli a0,1\nli a1,2\naddi a0,a0,3\naddi a1,a1,4\ncsrr a0,minstret\n'+finish,4,False,[]),
 'compressed':(stall+'li a0,0\nli a1,0\n.rept 8\naddi a0,a0,1\naddi a1,a1,2\n.endr\nadd a0,a0,a1\n'+finish,24,True,[]),
 'exception':('la t0,handler\ncsrw mtvec,t0\nli a0,1\nli a1,2\n.word 0\naddi a0,a0,4\nj done\nhandler: csrr t0,mepc\naddi t0,t0,4\ncsrw mepc,t0\nmret\ndone: add a0,a0,a1\n'+finish,7,False,[2]),
 'flush':('li a0,0\nli s0,16\n1: bnez s0,2f\nli t0,99\nsd t0,528(zero)\n2: addi a0,a0,1\naddi s0,s0,-1\nbnez s0,1b\n'+finish,16,False,[]),
 'load':('li t0,0x3000\nli t1,64\nsd t1,0(t0)\nld a0,0(t0)\naddi a1,zero,1\naddi a2,zero,2\nadd a0,a0,a1\nadd a0,a0,a2\n'+finish,67,False,[])}
 audits={}
 for name,(body,result,compressed,causes) in cases.items():
  stem='dual_'+name;suite.compile(stem,body,compressed=compressed);runs=suite.run(stem,signature=result,causes=causes,timings=[(1,0),(5,0),(1,3),(5,7),(20,3)])
  for _,ram in runs:assert words(ram,528,1)==[0]
  wave=f'build/{stem}.vcd';trace=f'build/{stem}-wave.trace.jsonl';subprocess.run([suite.simulator,f'build/{stem}.bin','5',wave,'3',trace],check=True,capture_output=True);verify_files(f'build/{stem}.bin',trace);audits[name]=audit(wave)
 # Inject an external IRQ exactly one cycle after a real paired issue.
 irq_body='la t0,handler\ncsrw mtvec,t0\nli t0,2048\ncsrw mie,t0\ncsrsi mstatus,8\n'+stall+'li a0,0\nli a1,0\n.rept 8\naddi a0,a0,1\naddi a1,a1,2\n.endr\nadd a0,a0,a1\n'+finish+'handler: li t1,2048\n1: csrr t0,mip\nand t0,t0,t1\nbnez t0,1b\nmret\n'
 suite.compile('dual_irq',irq_body);wave='build/dual_irq_baseline.vcd'
 subprocess.run([suite.simulator,'build/dual_irq.bin','5',wave,'3'],check=True,capture_output=True)
 signals=read_vcd(wave);first=next(i+1 for i,(t,v) in enumerate([(t,v) for t,v in signals['clk'] if v==1 and not value_at(signals['reset'],t,True)]) if value_at(signals['pair_fire'],t,True))
 suite.run('dual_irq',signature=24,causes=[(1<<63)|11],timings=[(5,3)],events=[(first+1,2048),(first+80,0)])
 irq_trace='build/dual_irq-native-l5-g3.trace.jsonl';irq_wave='build/dual_irq.vcd'
 subprocess.run([suite.simulator,'build/dual_irq.bin','5',irq_wave,'3','build/dual_irq-wave.trace.jsonl','build/dual_irq.irq.txt'],check=True,capture_output=True);verify_files('build/dual_irq.bin','build/dual_irq-wave.trace.jsonl');audits['irq']=audit(irq_wave)
 signals=read_vcd(irq_wave);edges=[t for t,v in signals['clk'] if v==1 and not value_at(signals['reset'],t,True)];t=edges[first];assert value_at(signals['xp_valid'],t,True) and value_at(signals['irq_stop'],t,True)
 assert audits['burst']['pair_issues']>0 and sum(x['dual_retire_cycles'] for x in audits.values())>0
 # The checker must reject malformed lane/timestamp order and wrong second writes.
 path=Path('build/dual_burst-native-l5-g0.trace.jsonl');records=[json.loads(x) for x in path.read_text().splitlines()];idx=next(i for i,r in enumerate(records) if r.get('retire_slot')==1);bad=0
 for field,value in [('retire_slot',0),('retire_slot',2),('cycle',records[idx]['cycle']+1),('wdata',records[idx]['wdata']^1),('next_pc',records[idx]['next_pc']+4)]:
  mutated=copy.deepcopy(records);mutated[idx][field]=value
  try:verify(Path('build/dual_burst.bin').read_bytes(),mutated,Path(str(path)+'.ram').read_bytes())
  except ValueError:bad+=1
 assert bad==5
 Path('build/dual-audit.json').write_text(json.dumps(audits,indent=2)+'\n');Path('build/dual-native-stats.json').write_text(json.dumps(suite.stats,indent=2)+'\n')
 print(f'DUAL ALU INTEGRATION PASS: {suite.runs} runs, {suite.commits} commits, {suite.traps} traps; 12 packet/hazard/IRQ/dual-retirement VCD audits; 5 malformed-trace rejections')
if __name__=='__main__':main()
