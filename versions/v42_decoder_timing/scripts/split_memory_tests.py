"""Split I/D path integration, serialization and controlled legacy comparison."""
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
    def run(name,body,signature,data='',causes=None):
        suite.compile(name,body,data);suite.run(name,signature=signature,causes=causes or [],timings=timings)
    run('split_stream','''
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
    assert suite.stats[-1]['instruction_hits_during_data_fill']>0
    run('split_load_store','''
        li t0,0x3000
        li t1,32
        li a0,0
    1:  ld t2,0(t0)
        addi t2,t2,1
        sd t2,0(t0)
        add a0,a0,t2
        addi t1,t1,-1
        bnez t1,1b
        sd a0,512(zero)
        SIM_EXIT
    ''',528,'.org 0x3000\n.dword 0,11')
    run('split_atomic_competition','''
        li t0,0x3000
        li t1,16
        li t2,1
        li a0,0
    1:  ld t3,0(t0)
        amoadd.d t4,t2,(t0)
        add a0,a0,t4
        addi t1,t1,-1
        bnez t1,1b
        ld t3,0(t0)
        add a0,a0,t3
        sd a0,512(zero)
        SIM_EXIT
    ''',136,'.org 0x3000\n.dword 0,11')
    run('split_fence_patch','''
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
    run('split_precise_fault','''
        la t0,handler
        csrw mtvec,t0
        li t0,0x3000
        ld a0,0(t0)
        li t1,0x10000
        ld a1,0(t1)
        sd zero,512(zero)
        SIM_EXIT
    ''',42,'''
        .org 0x800
    handler:
        sd a0,512(zero)
        SIM_EXIT
        .org 0x3000
        .dword 42,0
    ''',[5])
    rows=[]
    for latency,gap in [(1,0),(5,0),(5,3)]:
        results={}
        for mode,sim in [('split',suite.simulator),('legacy','build/unsplit_obj/Vrv64_core')]:
            trace=f'build/split-stream-{mode}-l{latency}-g{gap}.trace.jsonl'
            r=subprocess.run([sim,'build/split_stream.bin',str(latency),'-',str(gap),trace],check=True,capture_output=True,text=True)
            s=json.loads(r.stdout);assert s['result']==64 and verify_files('build/split_stream.bin',trace)==s['instret'];results[mode]=s
        on,off=results['split'],results['legacy']
        assert on['cycles']<off['cycles'] and on['instruction_hits_during_data_fill']>0
        assert off['instruction_hits_during_data_fill']==0
        rows.append(dict(latency=latency,gap=gap,split_cycles=on['cycles'],legacy_cycles=off['cycles'],
                         split_requests=on['requests'],legacy_requests=off['requests'],
                         instruction_hits_during_data_fill=on['instruction_hits_during_data_fill'],
                         split_frontend_starved=on['frontend_starved_cycles'],legacy_frontend_starved=off['frontend_starved_cycles']))
    with Path('build/split-memory-ablation.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    Path('build/split-memory-native-stats.json').write_text(json.dumps(suite.stats,indent=2)+'\n')
    subprocess.run([suite.simulator,'build/split_stream.bin','5','build/split-memory.vcd','3'],check=True,capture_output=True,text=True)
    print(f'SPLIT MEMORY INTEGRATION PASS: {suite.runs} runs, {suite.commits} commits, {suite.traps} traps; 6 split/legacy runs')


if __name__=='__main__':main()
