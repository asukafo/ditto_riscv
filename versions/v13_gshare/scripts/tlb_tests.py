"""Whole-core Sv39 locality, capacity, permission and invalidation tests."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
from native_test_support import NativeSuite,words
from reference import verify_files

BOOT='''
    li a0,0
    la t0,handler
    csrw mtvec,t0
    li t0,0x8000000000000006
    csrw satp,t0
    li t0,STATUS
    csrw mstatus,t0
    li t0,ENTRY
    csrw mepc,t0
    mret
'''
HANDLER='''
    .org 0x800
handler:
    csrr t0,mepc
    sd t0,768(zero)
    csrr t0,mtval
    sd t0,776(zero)
    sd a0,512(zero)
    SIM_EXIT
'''
TABLES='''
    .org 0x6000
    .dword 0,0x1c01
    .org 0x7000
    .dword 0x2001
    .org 0x8000
'''

def main():
    p=argparse.ArgumentParser();p.add_argument('--cross',default='riscv64-elf-');args=p.parse_args()
    suite=NativeSuite(args.cross);timings=[(1,0),(5,0),(1,3),(5,7),(20,3)]
    def run(name,program,signature,flags=0xc7,status=0x800,leaves=None,causes=None,entry=0x40000000,body=None):
        boot=BOOT.replace('STATUS',hex(status)).replace('ENTRY',hex(entry))
        data=body if body is not None else HANDLER+'\n.org 0x1000\n'+program+'\n.org 0x2000\n.dword 7\n.org 0x3000\n.dword 99\n'+TABLES+'\n.dword 0x44b,'+hex((2<<10)|flags)+((','+leaves) if leaves else '')
        suite.compile(name,boot,data)
        return suite.run(name,signature=signature,causes=causes or [9],timings=timings)
    run('tlb_loop','''
        li t0,0x40001000
        li t1,64
        li a0,0
    1:  ld t2,0(t0)
        add a0,a0,t2
        addi t1,t1,-1
        bnez t1,1b
        ecall
    ''',448)
    assert all(s['dtlb_hits']==63 and s['d_walk_reads']==3 and s['i_walk_reads']==3 for s in suite.stats[-5:])
    for pages,rounds in [(4,3),(10,2)]:
        code=f'''
            li a0,0
            li s0,4096
            li s1,{rounds}
        1:  li t0,0x40001000
            li t1,{pages}
        2:  ld t2,0(t0)
            add a0,a0,t2
            add t0,t0,s0
            addi t1,t1,-1
            bnez t1,2b
            addi s1,s1,-1
            bnez s1,1b
            ecall
        '''
        run(f'tlb_pages_{pages}',code,pages*rounds*7,leaves=','.join(['0x8c7']*(pages-1)))
        expected=pages*(rounds-1) if pages<=8 else 0
        assert all(s['dtlb_hits']==expected for s in suite.stats[-5:])
    run('tlb_sum_change','''
        li t0,0x40001000
        ld a0,0(t0)
        li t1,0x40000
        csrc sstatus,t1
        ld a0,0(t0)
        ecall
    ''',7,flags=0xd7,status=0x40800,causes=[13])
    assert all(s['dtlb_hits']==1 and s['d_walk_reads']==3 for s in suite.stats[-5:])
    run('tlb_mxr_change','''
        li t0,0x40001000
        ld a0,0(t0)
        li t1,0x80000
        csrc sstatus,t1
        ld a0,0(t0)
        ecall
    ''',7,flags=0xc9,status=0x80800,causes=[13])
    assert all(s['dtlb_hits']==1 for s in suite.stats[-5:])
    run('tlb_sfence_remap','''
        li t0,0x40001000
        ld a0,0(t0)
        li t1,0x40002000
        li t2,0xcc7
        sd t2,8(t1)
        sfence.vma t0,zero
        ld a0,0(t0)
        ecall
    ''',99,leaves='0x20c7')
    assert all(s['i_walk_reads']==6 and s['d_walk_reads']==9 for s in suite.stats[-5:])
    for mapped in (True,False):
        data=HANDLER+'''
            .org 0x1ffc
            .2byte 1
            .2byte 0x0513
            .org 0x3000
            .2byte 0x02a0
            .4byte 0x73
        '''+TABLES+f'.dword 0x44b,{0xc4b if mapped else 0:#x}'
        r=run('tlb_cross_page_'+str(int(mapped)),'',42 if mapped else 0,entry=0x40000ffc,body=data,causes=[9 if mapped else 12])
        if not mapped:
            for _,ram in r:assert words(ram,768,2)==[0x40000ffe,0x40001000]
        assert all(s['itlb_fills']==(2 if mapped else 1) for s in suite.stats[-5:])
    # SATP write changes ASID and mapping; its conservative flush must remove old entries.
    boot=BOOT.replace('STATUS','0x800').replace('ENTRY','0x40000000')
    data='''
        .org 0x800
    handler:
        bnez s4,finish
        li s4,1
        li t0,0x8008
        li t1,0xcc7
        sd t1,0(t0)
        li t0,0x8000100000000006
        csrw satp,t0
        csrr t0,mepc
        addi t0,t0,4
        csrw mepc,t0
        mret
    finish:
        sd a0,512(zero)
        SIM_EXIT
        .org 0x1000
        li t2,0x40001000
        ld a0,0(t2)
        ecall
        ld a0,0(t2)
        ecall
        .org 0x2000
        .dword 7
        .org 0x3000
        .dword 99
    '''+TABLES+'.dword 0x44b,0x8c7'
    suite.compile('tlb_satp_asid',boot,data);suite.run('tlb_satp_asid',signature=99,causes=[9,9],timings=timings)
    rows=[]
    for latency,gap in [(1,0),(5,0),(5,3)]:
        results={}
        for mode,sim in [('enabled',suite.simulator),('disabled','build/notlb_obj/Vrv64_core')]:
            trace=f'build/tlb-loop-{mode}-l{latency}-g{gap}.trace.jsonl'
            r=subprocess.run([sim,'build/tlb_loop.bin',str(latency),'-',str(gap),trace],check=True,capture_output=True,text=True)
            s=json.loads(r.stdout);assert s['result']==448 and verify_files('build/tlb_loop.bin',trace)==s['instret'];results[mode]=s
        on,off=results['enabled'],results['disabled']
        assert on['cycles']<off['cycles'] and on['i_walk_reads']<off['i_walk_reads'] and on['d_walk_reads']<off['d_walk_reads']
        assert off['itlb_hits']==off['dtlb_hits']==off['itlb_fills']==off['dtlb_fills']==0
        rows.append(dict(latency=latency,gap=gap,tlb_cycles=on['cycles'],disabled_cycles=off['cycles'],tlb_requests=on['requests'],disabled_requests=off['requests'],
                         i_walk_reads=on['i_walk_reads'],disabled_i_walk_reads=off['i_walk_reads'],d_walk_reads=on['d_walk_reads'],disabled_d_walk_reads=off['d_walk_reads']))
    with Path('build/tlb-ablation.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    Path('build/tlb-native-stats.json').write_text(json.dumps(suite.stats,indent=2)+'\n')
    subprocess.run([suite.simulator,'build/tlb_loop.bin','5','build/tlb.vcd','3'],check=True,capture_output=True,text=True)
    print(f'TLB INTEGRATION PASS: {suite.runs} runs, {suite.commits} commits, {suite.traps} traps; 6 on/off runs')


if __name__=='__main__':main()
