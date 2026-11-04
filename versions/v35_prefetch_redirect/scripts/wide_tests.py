"""Wide frontend native boundary cases plus measured, independently checked warm IPC."""
import json,subprocess,hashlib
from pathlib import Path
from native_test_support import NativeSuite,words
from reference import verify_files
from wide_audit import audit
from path_tests import audit as path_audit
from window_tests import audit as ownership_audit

def main():
 suite=NativeSuite();finish='sd a0,512(zero)\nSIM_EXIT\n'
 cases={
 'mixed':('li a0,0\nli a1,0\n.rept 16\nc.addi a0,1\n.option norvc\naddi a1,a1,2\n.option rvc\n.endr\nadd a0,a0,a1\n'+finish,48,True,[]),
 'second_control':('li a0,0\nli s0,16\n1: addi a0,a0,1\nbnez zero,2f\naddi s0,s0,-1\nbnez s0,1b\nj 3f\n2: sd s0,528(zero)\n3:\n'+finish,16,False,[]),
 'second_fault':('la t0,handler\ncsrw mtvec,t0\nli a0,0\n.balign 8\naddi a0,a0,7\n.word 0\naddi a0,a0,100\nhandler:\n'+finish,7,False,[2]),
 'self_modify':('la s0,func\njalr ra,0(s0)\nmv s1,a0\nli t0,0x02a00513\nsw t0,0(s0)\nfence.i\njalr ra,0(s0)\nadd a0,a0,s1\n'+finish+'.balign 8\nfunc: li a0,1\nret\n',43,False,[]),
 'load_use':('li t0,0x3000\nli a0,11\nsd a0,0(t0)\nld a1,0(t0)\naddi a2,a1,2\nadd a0,a1,a2\n'+finish,24,False,[]),
 'jump_half':('li a0,0\nc.nop\n.option norvc\njal zero,1f\naddi a0,a0,99\n1: addi a0,a0,7\n'+finish,7,True,[])}
 audits={}
 for name,(body,result,compressed,causes) in cases.items():
  stem='wide_'+name;suite.compile(stem,body,compressed=compressed);runs=suite.run(stem,signature=result,causes=causes,timings=[(1,0),(5,0),(1,3),(5,7),(20,3)])
  for _,ram in runs:assert words(ram,528,1)==[0]
  wave=f'build/{stem}.vcd';trace=f'build/{stem}-wave.trace.jsonl';subprocess.run([suite.simulator,f'build/{stem}.bin','5',wave,'3',trace],check=True,capture_output=True);verify_files(f'build/{stem}.bin',trace);audits[name]=audit(wave)
 warm={}
 for mode in ['full','narrow','onealu']:
  trace=f'build/wide-hot-{mode}.trace.jsonl';wave=f'build/wide-hot-{mode}.vcd';s=json.loads(subprocess.check_output([f'build/{mode}_obj/Vrv64_core','build/hot_alu.bin','5',wave,'3',trace],text=True));assert verify_files('build/hot_alu.bin',trace)==s['instret']==1300
  records=[json.loads(x) for x in Path(trace).read_text().splitlines()];commits=[x for x in records if x['kind']=='commit'];starts=[(i,x) for i,x in enumerate(commits) if x['pc']==36];a,b=starts[16],starts[112];instructions=b[0]-a[0];cycles=b[1]['cycle']-a[1]['cycle'];assert instructions==960
  warm[mode]=dict(cycles=s['cycles'],instret=s['instret'],paired_issues=s['dual_issue_pairs'],decode_pairs=s['wide_decode_pairs'],warm_instructions=instructions,warm_cycles=cycles,warm_ipc=instructions/cycles,anchor_cycle=a[1]['cycle'],trace_sha256=hashlib.sha256(Path(trace).read_bytes()).hexdigest(),vcd_sha256=hashlib.sha256(Path(wave).read_bytes()).hexdigest())
  if mode!='narrow':audits['hot_'+mode]=dict(packets=audit(wave),path=path_audit(wave),owners=ownership_audit(wave))
 assert warm['full']['warm_ipc']>1 and warm['narrow']['warm_ipc']==warm['onealu']['warm_ipc']==1
 assert warm['full']['warm_cycles']<warm['narrow']['warm_cycles'] and warm['full']['cycles']<warm['onealu']['cycles']
 assert sum(x.get('partial_accepts',0) for x in audits.values())>0
 Path('build/wide-audit.json').write_text(json.dumps(audits,indent=2)+'\n');Path('build/wide-warm-ipc.json').write_text(json.dumps(warm,indent=2)+'\n');Path('build/wide-native-stats.json').write_text(json.dumps(suite.stats,indent=2)+'\n')
 print(f'WIDE INTEGRATION PASS: {suite.runs} native runs, {suite.commits} commits, {suite.traps} traps; full-packet VCD models and 3 checked hot-loop runs; warm IPC={warm["full"]["warm_ipc"]:.6f}')
if __name__=='__main__':main()
