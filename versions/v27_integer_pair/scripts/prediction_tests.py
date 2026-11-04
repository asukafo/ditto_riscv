"""Static prediction, recovery, compressed assembly and speculative page faults."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
from native_test_support import NativeSuite,words
from reference import verify_files


def main():
    p=argparse.ArgumentParser();p.add_argument('--cross',default='riscv64-elf-');args=p.parse_args()
    suite=NativeSuite(args.cross);timings=[(1,0),(5,0),(1,3),(5,7),(20,3)]
    def run(name,body,signature,data='',causes=None,compressed=False):
        suite.compile(name,body,data,compressed=compressed)
        results=suite.run(name,signature=signature,causes=causes or [],timings=timings)
        for s in suite.stats[-len(timings):]:
            assert s['control_resolved']==s['conditional_branches']+s['direct_jumps']+s['indirect_jumps']
            assert s['control_misses']==s['conditional_misses']+s['direct_misses']+s['indirect_misses']
        return results
    run('predict_loop','''
        li a0,0
        li t0,32
    1:  addi a0,a0,1
        addi t0,t0,-1
        bnez t0,1b
        sd a0,512(zero)
        SIM_EXIT
    ''',32)
    assert all(s['conditional_branches']==32 and s['conditional_misses']==1 and s['predicted_redirects']==32 for s in suite.stats[-5:])
    r=run('predict_forward_taken','''
        li t0,0x3000
        beq zero,zero,target
        sd zero,0(t0)
        .word 0
    target:
        li a0,42
        sd a0,512(zero)
        SIM_EXIT
    ''',42,'.org 0x3000\n.dword 7')
    for _,ram in r:assert words(ram,0x3000,1)==[7]
    assert all(s['conditional_misses']==1 for s in suite.stats[-5:])
    run('predict_forward_not_taken','''
        bne zero,zero,bad
        li a0,42
        sd a0,512(zero)
        SIM_EXIT
    bad:
        .word 0
    ''',42)
    assert all(s['conditional_misses']==0 for s in suite.stats[-5:])
    r=run('predict_backward_not_taken','''
        li t0,0x3000
        jal zero,check
    bad:
        sd zero,0(t0)
        .word 0
    check:
        bne zero,zero,bad
        li a0,42
        sd a0,512(zero)
        SIM_EXIT
    ''',42,'.org 0x3000\n.dword 7')
    for _,ram in r:assert words(ram,0x3000,1)==[7]
    assert all(s['conditional_misses']==1 and s['direct_misses']==0 for s in suite.stats[-5:])
    run('predict_jal_link','''
        auipc t0,0
        jal ra,target
        .word 0
    target:
        sub a0,ra,t0
        sd a0,512(zero)
        SIM_EXIT
    ''',8)
    run('predict_halfword_jal','''
        c.nop
        .option norvc
        jal ra,target
        .word 0
    target:
        mv a0,ra
        sd a0,512(zero)
        SIM_EXIT
    ''',6,compressed=True)
    run('predict_jalr','''
        la t0,target
        jalr ra,0(t0)
        .word 0
    target:
        li a0,42
        sd a0,512(zero)
        SIM_EXIT
    ''',42)
    assert all(s['indirect_jumps']==1 and s['indirect_misses']==1 for s in suite.stats[-5:])
    run('predict_compressed_loop','''
        li a0,0
        li s0,32
    1:  c.addi a0,1
        c.addi s0,-1
        c.bnez s0,1b
        sd a0,512(zero)
        SIM_EXIT
    ''',32,compressed=True)
    assert all(s['conditional_branches']==32 and s['conditional_misses']==1 for s in suite.stats[-5:])
    run('predict_compressed_jump','''
        c.nop
        c.j target
        .word 0
    target:
        li a0,42
        sd a0,512(zero)
        SIM_EXIT
    ''',42,compressed=True)
    assert all(s['direct_misses']==0 for s in suite.stats[-5:])
    boot='''
        la t0,handler
        csrw mtvec,t0
        li t0,0x8000000000000006
        csrw satp,t0
        li t0,0x800
        csrw mstatus,t0
        li t0,ENTRY
        csrw mepc,t0
        mret
    '''
    handler='''
        .org 0x800
    handler:
        csrr t0,mepc
        sd t0,768(zero)
        csrr t0,mtval
        sd t0,776(zero)
        sd a0,512(zero)
        SIM_EXIT
    '''
    tables='''
        .org 0x6000
        .dword 0,0x1c01
        .org 0x7000
        .dword 0x2001
        .org 0x8000
        .dword LEAF0,LEAF1
    '''
    # BNE x0,x0,-4096 predicts an unmapped previous page but must fall through.
    run('predict_speculative_page_fault',boot.replace('ENTRY','0x40001000'),42,
        handler+'''.org 0x1000
        .4byte 0x80001063
        li a0,42
        ecall
        '''+tables.replace('LEAF0','0').replace('LEAF1','0x44b'),[9])
    # The real JAL target faults; the exception PC is target, not the jumping instruction.
    r=run('predict_real_target_fault',boot.replace('ENTRY','0x40000000'),42,
        handler+'''.org 0x1000
        li a0,42
        .4byte 0x7fd0006f
        '''+tables.replace('LEAF0','0x44b').replace('LEAF1','0'),[12])
    for _,ram in r:assert words(ram,768,2)==[0x40001000,0x40001000]
    rows=[]
    for name in ('predict_loop','predict_compressed_loop'):
        for latency,gap in [(1,0),(5,0),(5,3)]:
            results={}
            for mode,sim in [('enabled',suite.simulator),('disabled','build/nopredict_obj/Vrv64_core')]:
                trace=f'build/{name}-{mode}-l{latency}-g{gap}.trace.jsonl'
                r=subprocess.run([sim,f'build/{name}.bin',str(latency),'-',str(gap),trace],check=True,capture_output=True,text=True)
                s=json.loads(r.stdout);assert s['result']==32 and verify_files(f'build/{name}.bin',trace)==s['instret'];results[mode]=s
            on,off=results['enabled'],results['disabled']
            assert on['cycles']<off['cycles'] and on['conditional_misses']==1 and off['conditional_misses']==31
            rows.append(dict(program=name,latency=latency,gap=gap,predict_cycles=on['cycles'],disabled_cycles=off['cycles'],
                predict_misses=on['control_misses'],disabled_misses=off['control_misses'],predict_flushes=on['flush_count'],disabled_flushes=off['flush_count']))
    with Path('build/prediction-ablation.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    Path('build/prediction-native-stats.json').write_text(json.dumps(suite.stats,indent=2)+'\n')
    subprocess.run([suite.simulator,'build/predict_loop.bin','5','build/prediction.vcd','3'],check=True,capture_output=True,text=True)
    print(f'PREDICTION INTEGRATION PASS: {suite.runs} runs, {suite.commits} commits, {suite.traps} traps; 12 on/off runs')


if __name__=='__main__':main()
