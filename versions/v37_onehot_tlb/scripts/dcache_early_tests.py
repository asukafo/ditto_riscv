"""Whole-core checks for D-cache early response and subsequent memory operations."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
from native_test_support import NativeSuite
from reference import verify_files


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--cross',default='riscv64-elf-');args=parser.parse_args()
    suite=NativeSuite(args.cross);timings=[(1,0),(5,0),(1,3),(5,7),(20,3)]
    def run(name,body,signature,data):
        suite.compile(name,body,data)
        suite.run(name,signature=signature,causes=[],timings=timings)
    run('data_early_stream','''
        li t0,0x3000
        li t1,64
        li a0,0
    1:  ld t2,0(t0)
        add a0,a0,t2
        addi t0,t0,8
        addi t1,t1,-1
        bnez t1,1b
        sd a0,512(zero)
        SIM_EXIT
    ''',64,'.org 0x3000\n.rept 64\n.dword 1\n.endr')
    run('data_early_high_first','''
        li t0,0x3000
        ld a0,8(t0)
        ld t1,0(t0)
        add a0,a0,t1
        ld t1,16(t0)
        add a0,a0,t1
        sd a0,512(zero)
        SIM_EXIT
    ''',42,'.org 0x3000\n.dword 7,11,24,0')
    run('data_early_store_after','''
        li t0,0x3000
        ld t1,0(t0)
        li t2,42
        sd t2,0(t0)
        ld a0,0(t0)
        sd a0,512(zero)
        SIM_EXIT
    ''',42,'.org 0x3000\n.dword 7,11')
    run('data_early_atomic_after','''
        li t0,0x3000
        ld t1,0(t0)
        li t2,5
        amoadd.d t3,t2,(t0)
        ld a0,0(t0)
        add a0,a0,t3
        sd a0,512(zero)
        SIM_EXIT
    ''',19,'.org 0x3000\n.dword 7,11')
    run('data_early_patch_after','''
        la t0,func
        jalr ra,0(t0)
        ld t1,0(t0)
        li t2,0x02a00513
        sw t2,0(t0)
        fence.i
        jalr ra,0(t0)
        sd a0,512(zero)
        SIM_EXIT
    ''',42,'.org 0x1000\nfunc:\naddi a0,zero,1\nret')
    rows=[]
    for name in ('data_early_stream','data_early_high_first'):
        for latency,gap in [(1,0),(5,0),(5,3)]:
            results={}
            for mode,sim in [('enabled',suite.simulator),('disabled','build/nodataearly_obj/Vrv64_core')]:
                trace=f'build/{name}-{mode}-l{latency}-g{gap}.trace.jsonl'
                r=subprocess.run([sim,f'build/{name}.bin',str(latency),'-',str(gap),trace],check=True,capture_output=True,text=True)
                s=json.loads(r.stdout);assert verify_files(f'build/{name}.bin',trace)==s['instret']
                results[mode]=s
            on,off=results['enabled'],results['disabled']
            # Frontend lookahead can issue a different speculative instruction tail.
            # Compare data refill work, not the aggregate physical request count.
            assert on['result']==off['result'] and on['dcache_refill_requests']==off['dcache_refill_requests']
            assert on['data_wait']<off['data_wait'],(name,latency,gap,on,off)
            rows.append(dict(program=name,latency=latency,gap=gap,early_cycles=on['cycles'],disabled_cycles=off['cycles'],
                             requests=on['requests'],disabled_requests=off['requests'],early_data_wait=on['data_wait'],disabled_data_wait=off['data_wait']))
    assert any(r['early_cycles']<r['disabled_cycles'] for r in rows)
    with Path('build/dcache-early-ablation.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    Path('build/dcache-early-native-stats.json').write_text(json.dumps(suite.stats,indent=2)+'\n')
    subprocess.run([suite.simulator,'build/data_early_stream.bin','5','build/dcache-early.vcd','3'],check=True,capture_output=True,text=True)
    print(f'DCACHE EARLY INTEGRATION PASS: {suite.runs} runs, {suite.commits} commits, {suite.traps} traps; 12 on/off runs')


if __name__=='__main__':main()
