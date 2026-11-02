"""Data cache integration with independent commit/RAM checks and disabled-cache controls."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
from native_test_support import NativeSuite,words
from reference import verify_files


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--cross',default='riscv64-elf-');args=parser.parse_args()
    suite=NativeSuite(args.cross);timings=[(1,0),(5,0),(1,3),(5,7),(20,3)]
    def run(name,body,signature,data='',causes=None):
        suite.compile(name,body,data)
        return suite.run(name,signature=signature,causes=causes or [],timings=timings)
    run('dcache_reuse','''
        li t0,0x3000
        li t1,128
        li a0,0
    1:  ld t2,0(t0)
        add a0,a0,t2
        addi t1,t1,-1
        bnez t1,1b
        sd a0,512(zero)
        SIM_EXIT
    ''',896,'.org 0x3000\n.dword 7,11')
    assert suite.stats[-1]['dcache_hits']>=127 and suite.stats[-1]['dcache_misses']==1
    results=run('dcache_store_widths','''
        li t0,0x3000
        ld t1,0(t0)
        li t2,0x12345678
        sb t2,1(t0)
        sh t2,2(t0)
        sw t2,4(t0)
        ld a0,0(t0)
        sd a0,512(zero)
        SIM_EXIT
    ''',0x12345678567878ff,'.org 0x3000\n.dword -1,11')
    for _,ram in results:assert words(ram,0x3000,2)==[0x12345678567878ff,11]
    run('dcache_conflicts','''
        li t0,0x3000
        li t1,16
        li a0,0
    1:  ld t2,0(t0)
        ld t3,256(t0)
        add a0,a0,t2
        add a0,a0,t3
        addi t1,t1,-1
        bnez t1,1b
        sd a0,512(zero)
        SIM_EXIT
    ''',48,'.org 0x3000\n.dword 1\n.org 0x3100\n.dword 2')
    run('dcache_atomic_alias','''
        li t0,0x3000
        ld t1,0(t0)
        li t2,5
        amoadd.d a0,t2,(t0)
        ld t3,0(t0)
        add a0,a0,t3
        lr.d t4,(t0)
        li t2,9
        sc.d t5,t2,(t0)
        ld t3,0(t0)
        add a0,a0,t3
        sc.d t5,t2,(t0)
        add a0,a0,t5
        sd a0,512(zero)
        SIM_EXIT
    ''',29,'.org 0x3000\n.dword 7,0')
    run('dcache_mailbox_boundary','''
        li t0,0xffe8
        li t1,42
        sd t1,0(t0)
        ld t2,0(t0)
        li t0,0xfff8
        sd t1,0(t0)
        ld a0,0(t0)
        sd a0,512(zero)
        SIM_EXIT
    ''',42)
    for name,flags,cause,signature in [('dcache_warm_permission',0xc7,13,0),
                                       ('dcache_warm_alias',0xd7,8,42)]:
        run(name,f'''
            la t0,handler
            csrw mtvec,t0
            li t0,0x2000
            ld a0,0(t0)
            li t0,{(8<<60)|6:#x}
            csrw satp,t0
            csrw mstatus,zero
            li t0,0x40000000
            csrw mepc,t0
            mret
        ''',signature,f'''
            .org 0x800
        handler:
            sd a0,512(zero)
            SIM_EXIT
            .org 0x1000
            li a0,0
            li t0,0x40001000
            ld a0,0(t0)
            ecall
            .org 0x2000
            .dword 42
            .org 0x6000
            .dword 0,0x1c01
            .org 0x7000
            .dword 0x2001
            .org 0x8000
            .dword 0x45b,{(2<<10)|flags:#x}
        ''',[cause])
    run('dcache_pte_write_through',f'''
        la t0,handler
        csrw mtvec,t0
        li t0,0x8008
        ld t1,0(t0)
        li t1,{(3<<10)|0xc7:#x}
        sd t1,0(t0)
        sfence.vma
        li t0,{(8<<60)|6:#x}
        csrw satp,t0
        li t0,0x800
        csrw mstatus,t0
        li t0,0x40000000
        csrw mepc,t0
        mret
    ''',99,'''
        .org 0x800
    handler:
        sd a0,512(zero)
        SIM_EXIT
        .org 0x1000
        li t0,0x40001000
        ld a0,0(t0)
        ecall
        .org 0x2000
        .dword 42
        .org 0x3000
        .dword 99
        .org 0x6000
        .dword 0,0x1c01
        .org 0x7000
        .dword 0x2001
        .org 0x8000
        .dword 0x44b,0x8c7
    ''',[9])
    rows=[]
    for latency,gap in [(1,0),(5,0),(5,3)]:
        stats={}
        for mode,sim in [('enabled',suite.simulator),('disabled','build/nodcache_obj/Vrv64_core')]:
            trace=f'build/dcache-reuse-{mode}-l{latency}-g{gap}.trace.jsonl'
            r=subprocess.run([sim,'build/dcache_reuse.bin',str(latency),'-',str(gap),trace],check=True,capture_output=True,text=True)
            s=json.loads(r.stdout);assert s['result']==896 and verify_files('build/dcache_reuse.bin',trace)==s['instret']
            stats[mode]=s
        on,off=stats['enabled'],stats['disabled']
        assert on['requests']<off['requests']
        if latency>1:assert on['cycles']<off['cycles']
        assert off['dcache_hits']==off['dcache_misses']==0
        rows.append(dict(latency=latency,gap=gap,cache_cycles=on['cycles'],disabled_cycles=off['cycles'],
                         cache_requests=on['requests'],disabled_requests=off['requests'],hits=on['dcache_hits'],misses=on['dcache_misses']))
    with Path('build/dcache-ablation.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    Path('build/dcache-native-stats.json').write_text(json.dumps(suite.stats,indent=2)+'\n')
    subprocess.run([suite.simulator,'build/dcache_reuse.bin','5','build/dcache.vcd','3'],check=True,capture_output=True,text=True)
    print(f'DCACHE INTEGRATION PASS: {suite.runs} runs, {suite.commits} commits, {suite.traps} traps; 6 on/off runs')


if __name__=='__main__':main()
