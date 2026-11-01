"""Committed return history: calls, nesting, overflow, recovery and serial clear."""
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
    def run(name,body,signature,data='',compressed=False,causes=None):
        suite.compile(name,body,data,compressed=compressed)
        results=suite.run(name,signature=signature,causes=causes or [],timings=timings)
        for s in suite.stats[-5:]:assert s['ras_misses']<=s['ras_predictions'] and s['ras_misses']<=s['indirect_misses']
        return results
    run('ras_calls','''
        li s0,16
        li a0,0
    1:  jal ra,func
        addi s0,s0,-1
        bnez s0,1b
        sd a0,512(zero)
        SIM_EXIT
    func:
        .rept 4
        addi a0,a0,1
        .endr
        ret
    ''',64)
    assert all(s['ras_predictions']==16 and s['ras_misses']==0 and s['indirect_misses']==0 for s in suite.stats[-5:])
    run('ras_nested','''
        li s0,8
        li a0,0
    1:  jal ra,outer
        addi s0,s0,-1
        bnez s0,1b
        sd a0,512(zero)
        SIM_EXIT
    outer:
        mv s1,ra
        jal ra,middle
        mv ra,s1
        addi a0,a0,1
        ret
    middle:
        mv s2,ra
        jal ra,leaf
        mv ra,s2
        addi a0,a0,1
        ret
    leaf:
        addi a0,a0,1
        nop
        ret
    ''',24)
    assert all(s['ras_pushes']==24 and s['ras_pops']==24 and s['ras_overflows']==0 for s in suite.stats[-5:])
    run('ras_compressed','''
        la s0,func
        li s1,8
        li a0,0
    1:  c.jalr s0
        c.addi s1,-1
        c.bnez s1,1b
        sd a0,512(zero)
        SIM_EXIT
    func:
        c.addi a0,1
        c.nop
        c.jr ra
    ''',8,compressed=True)
    run('ras_alternate_link','''
        li s0,8
        li a0,0
    1:  jal t0,func
        addi s0,s0,-1
        bnez s0,1b
        sd a0,512(zero)
        SIM_EXIT
    func:
        addi a0,a0,1
        nop
        jalr zero,0(t0)
    ''',8)
    assert all(s['ras_predictions']==8 and s['ras_misses']==0 for s in suite.stats[-5:])
    nested='li s7,0x4000\nli a0,0\njal ra,f0\nsd a0,512(zero)\nSIM_EXIT\n'
    for i in range(12):
        nested+=f'f{i}:\n'
        if i<11:nested+=f'sd ra,{i*8}(s7)\njal ra,f{i+1}\nld ra,{i*8}(s7)\n'
        nested+='addi a0,a0,1\nnop\nret\n'
    run('ras_overflow',nested,12)
    assert all(s['ras_overflows']==4 and s['ras_underflows']==4 for s in suite.stats[-5:])
    run('ras_underflow','''
        la ra,target
        ret
        .word 0
    target:
        li a0,42
        sd a0,512(zero)
        SIM_EXIT
    ''',42)
    assert all(s['ras_predictions']==0 and s['ras_underflows']==1 for s in suite.stats[-5:])
    r=run('ras_wrong_path_call','''
        li s0,0x3000
        beq zero,zero,target
        jal ra,bad
        .word 0
    target:
        jal ra,func
        sd a0,512(zero)
        SIM_EXIT
    func:
        li a0,42
        nop
        ret
    bad:
        sd zero,0(s0)
        .word 0
    ''',42,'.org 0x3000\n.dword 7')
    for _,ram in r:assert words(ram,0x3000,1)==[7]
    assert all(s['ras_pushes']==1 and s['ras_pops']==1 for s in suite.stats[-5:])
    r=run('ras_modified_link','''
        li s0,0x3000
        jal ra,func
        sd zero,0(s0)
        .word 0
    func:
        la ra,recover
        nop
        ret
    recover:
        li a0,42
        sd a0,512(zero)
        SIM_EXIT
    ''',42,'.org 0x3000\n.dword 7')
    for _,ram in r:assert words(ram,0x3000,1)==[7]
    assert all(s['ras_predictions']==1 and s['ras_misses']==1 for s in suite.stats[-5:])
    run('ras_serial_clear','''
        jal ra,func
        sd a0,512(zero)
        SIM_EXIT
    func:
        csrr zero,mhartid
        li a0,42
        ret
    ''',42)
    assert all(s['ras_predictions']==0 and s['ras_underflows']==1 for s in suite.stats[-5:])
    run('ras_trap_clear','''
        la t0,handler
        csrw mtvec,t0
        jal ra,func
        sd a0,512(zero)
        SIM_EXIT
    func:
        li a0,42
        ecall
        ret
    handler:
        csrr t0,mepc
        addi t0,t0,4
        csrw mepc,t0
        mret
    ''',42,causes=[11])
    assert all(s['ras_predictions']==0 and s['ras_underflows']==1 for s in suite.stats[-5:])
    rows=[]
    for name in ('ras_calls','ras_nested'):
        for latency,gap in [(1,0),(5,0),(5,3)]:
            results={}
            for mode,sim in [('enabled',suite.simulator),('disabled','build/noras_obj/Vrv64_core')]:
                trace=f'build/{name}-{mode}-l{latency}-g{gap}.trace.jsonl'
                r=subprocess.run([sim,f'build/{name}.bin',str(latency),'-',str(gap),trace],check=True,capture_output=True,text=True)
                s=json.loads(r.stdout);assert verify_files(f'build/{name}.bin',trace)==s['instret'];results[mode]=s
            on,off=results['enabled'],results['disabled']
            assert on['result']==off['result'] and on['cycles']<off['cycles'] and on['indirect_misses']<off['indirect_misses']
            assert off['ras_predictions']==off['ras_pushes']==off['ras_pops']==0
            rows.append(dict(program=name,latency=latency,gap=gap,ras_cycles=on['cycles'],disabled_cycles=off['cycles'],
                             predictions=on['ras_predictions'],ras_misses=on['ras_misses'],indirect_misses=on['indirect_misses'],disabled_indirect_misses=off['indirect_misses']))
    with Path('build/ras-ablation.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    Path('build/ras-native-stats.json').write_text(json.dumps(suite.stats,indent=2)+'\n')
    subprocess.run([suite.simulator,'build/ras_calls.bin','5','build/ras.vcd','3'],check=True,capture_output=True,text=True)
    print(f'RAS INTEGRATION PASS: {suite.runs} runs, {suite.commits} commits, {suite.traps} traps; 12 on/off runs')


if __name__=='__main__':main()
