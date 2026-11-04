"""Retired branch training, adaptation, aliases and wrong-path isolation."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
from native_test_support import NativeSuite
from reference import verify_files


def main():
    p=argparse.ArgumentParser();p.add_argument('--cross',default='riscv64-elf-');args=p.parse_args()
    suite=NativeSuite(args.cross);timings=[(1,0),(5,0),(1,3),(5,7),(20,3)]
    def run(name,body,signature,compressed=False):
        suite.compile(name,body,compressed=compressed)
        results=suite.run(name,signature=signature,causes=[],timings=timings)
        for (records,_),s in zip(results,suite.stats[-5:]):
            # These cases have only ordinary 32-bit branches except the explicit C case.
            branches=[r for r in records if r['kind']=='commit' and
                      ((r['insn']&127)==0x63 or (compressed and r['bytes']==2 and (r['insn']&0xe003) in (0xc001,0xe001)))]
            assert s['bht_trains']==len(branches),(name,s['bht_trains'],len(branches))
            assert s['bht_misses']<=s['bht_predictions']<=s['conditional_branches']
        return suite.stats[-5:]
    finish='sd a0,512(zero)\nSIM_EXIT\n'
    for name,condition in [('forward','beq t2,zero,2f'),('alternating','andi t0,s0,1\nbnez t0,2f'),
                           ('phase','slti t0,s0,33\nbnez t0,2f')]:
        run('bht_'+name,'li s0,64\nli a0,0\n1:\n'+condition+'''
        addi a0,a0,1
    2:  addi a0,a0,1
        addi s0,s0,-1
        bnez s0,1b
        '''+finish,64 if name=='forward' else 96)
    run('bht_backward_not_taken','''
        li s0,64
        li a0,0
        j 2f
    1:  addi a0,a0,100
    2:  bnez zero,1b
        addi a0,a0,1
        addi s0,s0,-1
        bnez s0,2b
    '''+finish,64)
    s=run('bht_offset4','''
        li s0,32
        li a0,0
    1:  beq zero,zero,2f
    2:  addi a0,a0,1
        addi s0,s0,-1
        bnez s0,1b
    '''+finish,32)
    assert all(x['bht_taken']==63 and x['bht_trains']==64 for x in s)
    run('bht_wrong_path','''
        li s0,32
        li a0,0
    1:  beq zero,zero,2f
        bne zero,zero,dead
        .word 0
    2:  addi a0,a0,1
        addi s0,s0,-1
        bnez s0,1b
    '''+finish+'''dead: .word 0
    ''',32)
    # A/B at the same PC[5:1] repeatedly train opposite outcomes.
    run('bht_alias','''
        li s0,32
        li a0,0
        j A
        .balign 64
    A:  beq zero,zero,B
        .word 0
        .balign 64
    B:  bne zero,zero,dead
        addi a0,a0,1
        addi s0,s0,-1
        bnez s0,A
    '''+finish+'''dead: .word 0
    ''',32)
    run('bht_compressed','''
        li s0,32
        li a0,0
    1:  c.beqz s1,2f
        c.addi a0,1
    2:  c.addi a0,1
        c.addi s0,-1
        c.bnez s0,1b
    '''+finish,32,compressed=True)
    s=run('bht_serial_clear','''
        li s0,8
        li a0,0
    1:  beq zero,zero,2f
        .word 0
    2:  fence.i
        addi a0,a0,1
        addi s0,s0,-1
        bnez s0,1b
    '''+finish,8)
    # Serial flush clears the table; only the loop branch can seed the next iteration.
    assert all(x['bht_trains']==16 for x in s)
    rows=[]
    for name in ('forward','backward_not_taken','phase','alternating','alias','compressed'):
        for latency,gap in [(1,0),(5,0),(5,3)]:
            pair=[]
            for mode,sim in [('enabled',suite.simulator),('disabled','build/nobht_obj/Vrv64_core')]:
                trace=f'build/bht-{name}-{mode}-l{latency}-g{gap}.trace.jsonl'
                s=json.loads(subprocess.check_output([sim,f'build/bht_{name}.bin',str(latency),'-',str(gap),trace],text=True))
                assert verify_files(f'build/bht_{name}.bin',trace)==s['instret'];pair.append(s)
            on,off=pair
            assert on['result']==off['result'] and on['instret']==off['instret']
            assert off['bht_enabled']==off['bht_trains']==off['bht_predictions']==0
            if name=='forward':assert on['cycles']<off['cycles'] and on['conditional_misses']<off['conditional_misses']
            rows.append(dict(program=name,latency=latency,gap=gap,bht_cycles=on['cycles'],static_cycles=off['cycles'],
                bht_misses=on['conditional_misses'],static_misses=off['conditional_misses'],dynamic_predictions=on['bht_predictions']))
    with Path('build/bht-ablation.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    Path('build/bht-native-stats.json').write_text(json.dumps(suite.stats,indent=2)+'\n')
    subprocess.run([suite.simulator,'build/bht_forward.bin','5','build/bht.vcd','3'],check=True,capture_output=True,text=True)
    print(f'BHT INTEGRATION PASS: {suite.runs} runs, {suite.commits} commits, {suite.traps} traps; 36 on/off runs')


if __name__=='__main__':main()
