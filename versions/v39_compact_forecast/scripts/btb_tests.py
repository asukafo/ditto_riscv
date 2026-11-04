"""Real programs for last-target prediction, recovery, conflicts and FENCE.I."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
from native_test_support import NativeSuite
from reference import verify_files
from waveforms import read_vcd,value_at


def audit(path):
    core=read_vcd(path);front=read_vcd(path,['TOP','rv64_core','frontend']);table=[None]*32;queries=hits=early=0
    for stamp,value in core['clk']:
        if value!=1 or value_at(core['reset'],stamp,True):continue
        pre=lambda name:value_at(core[name],stamp,True)
        if pre('btb_lookup_event'):
            pc=pre('unused_fe_query_pc');entry=table[(pc>>1)&31];hit=entry is not None and entry['pc']==pc and not pc&1
            assert pre('btb_hit_event')==hit
            assert value_at(front['early_hit'],stamp)==hit
            if hit:
                hits+=1;early+=not pre('raw_fe_valid') or pre('raw_fe_pc')!=pc
                for key,signal in [('target','early_target'),('kind','early_kind'),('bytes','early_bytes')]:
                    assert value_at(front[signal],stamp)==entry[key],(stamp,key,entry)
                assert value_at(front['early_index'],stamp)==(((pc>>1)&31)^pre('global_history'))
                if entry['kind']==4:assert value_at(front['early_next'],stamp)==entry['target']
            queries+=1
        if pre('trap_enter') or (pre('retire') and pre('wb_serial')):table=[None]*32
        elif pre('btb_train_event'):
            pc=pre('wb_pc');insn=pre('wb_insn');op=insn&127;target=pre('wb_next');kind=4
            if op==0x63:
                kind=1;offset=((insn>>31)<<12)|(((insn>>7)&1)<<11)|(((insn>>25)&63)<<5)|(((insn>>8)&15)<<1)
                if offset&4096:offset-=8192
                target=(pc+offset)&((1<<64)-1)
            elif op==0x6f:
                kind=2;offset=((insn>>31)<<20)|(((insn>>12)&255)<<12)|(((insn>>20)&1)<<11)|(((insn>>21)&1023)<<1)
                if offset&1048576:offset-=2097152
                target=(pc+offset)&((1<<64)-1)
            elif (insn>>7)&31==0 and (insn>>15)&31 in (1,5) and insn>>20==0:kind=3
            table[(pc>>1)&31]=dict(pc=pc,target=target,kind=kind,bytes=pre('wb_bytes'))
    assert hits>0 and early>0,(queries,hits,early)
    return dict(queries=queries,hits=hits,hits_before_instruction_packet=early)


def main():
    p=argparse.ArgumentParser();p.add_argument('--cross',default='riscv64-elf-');args=p.parse_args()
    suite=NativeSuite(args.cross);timings=[(1,0),(5,0),(1,3),(5,7),(20,3)]
    finish='sd a0,512(zero)\nSIM_EXIT\n'
    cases={
      'indirect':('''li s0,16
        li a0,0
        la s1,func
    1:  jalr ra,0(s1)
        addi s0,s0,-1
        bnez s0,1b
    '''+finish+'''func:
        .rept 4
        addi a0,a0,1
        .endr
        ret
    ''',64,False),
      'changing':('''li s0,32
        li a0,0
    1:  andi t0,s0,1
        la s1,f1
        beqz t0,2f
        la s1,f2
    2:  jalr ra,0(s1)
        addi s0,s0,-1
        bnez s0,1b
    '''+finish+'''f1: addi a0,a0,1
        ret
    f2: addi a0,a0,2
        ret
    ''',48,False),
      'phase':('''li s0,32
        li a0,0
        la s1,f1
    1:  li t0,16
        bne s0,t0,2f
        la s1,f2
    2:  jalr ra,0(s1)
        addi s0,s0,-1
        bnez s0,1b
    '''+finish+'''f1: addi a0,a0,1
        ret
    f2: addi a0,a0,2
        ret
    ''',48,False),
      'self_modify':('''li s0,16
        li a0,0
        la s1,func
    1:  jalr ra,0(s1)
        addi s0,s0,-1
        bnez s0,1b
        li t0,0x00250513
        sw t0,0(s1)
        fence.i
        li s0,16
    2:  jalr ra,0(s1)
        addi s0,s0,-1
        bnez s0,2b
    '''+finish+'''func: addi a0,a0,1
        nop
        ret
    ''',48,False),
      'compressed':('''li s0,16
        li a0,0
        la s1,func
    1:  c.jalr s1
        c.addi s0,-1
        c.bnez s0,1b
    '''+finish+'''func: c.addi a0,1
        c.nop
        c.jr ra
    ''',16,True),
      'alias':('''li s0,16
        li a0,0
        la s1,f1
        la s2,f2
        j A
        .balign 64
    A:  jalr ra,0(s1)
        j B
        .balign 64
    B:  jalr ra,0(s2)
        addi s0,s0,-1
        bnez s0,A
    '''+finish+'''f1: addi a0,a0,1
        ret
    f2: addi a0,a0,2
        ret
    ''',48,False),
    }
    for name,(body,signature,compressed) in cases.items():
        suite.compile('btb_'+name,body,compressed=compressed)
        results=suite.run('btb_'+name,signature=signature,causes=[],timings=timings)
        for (records,_),stats in zip(results,suite.stats[-5:]):
            assert stats['btb_enabled']==1 and stats['btb_misses']<=stats['btb_predictions'] and stats['btb_hits']<=stats['btb_lookups']
            if not compressed:
                controls=sum(r['kind']=='commit' and r['insn']&127 in (0x63,0x67,0x6f) for r in records)
                assert stats['btb_trains']==controls
    rows=[]
    for name in cases:
        for latency,gap in [(1,0),(5,0),(5,3)]:
            pair=[]
            for mode,sim in [('btb',suite.simulator),('disabled','build/nobtb_obj/Vrv64_core')]:
                trace=f'build/btb-{name}-{mode}-l{latency}-g{gap}.trace.jsonl'
                stats=json.loads(subprocess.check_output([sim,f'build/btb_{name}.bin',str(latency),'-',str(gap),trace],text=True))
                assert verify_files(f'build/btb_{name}.bin',trace)==stats['instret'];pair.append(stats)
            on,off=pair;assert on['result']==off['result'] and on['instret']==off['instret']
            assert off['btb_enabled']==off['btb_trains']==off['btb_predictions']==off['btb_hits']==0
            if name=='indirect':assert on['indirect_misses']<off['indirect_misses'] and on['cycles']<off['cycles']
            rows.append(dict(program=name,latency=latency,gap=gap,btb_cycles=on['cycles'],disabled_cycles=off['cycles'],btb_control_misses=on['control_misses'],disabled_control_misses=off['control_misses'],btb_indirect_misses=on['indirect_misses'],disabled_indirect_misses=off['indirect_misses']))
    with Path('build/btb-ablation.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    Path('build/btb-native-stats.json').write_text(json.dumps(suite.stats,indent=2)+'\n')
    subprocess.run([suite.simulator,'build/btb_indirect.bin','5','build/btb.vcd','3'],check=True,capture_output=True,text=True)
    Path('build/btb-query-audit.json').write_text(json.dumps(audit('build/btb.vcd'),indent=2)+'\n')
    print(f'BTB INTEGRATION PASS: {suite.runs} runs, {suite.commits} commits, {suite.traps} traps; 36 on/off runs')


if __name__=='__main__':main()
