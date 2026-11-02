"""Halfword reuse, mixed widths, page faults, context changes and buffer on/off."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
from native_test_support import NativeSuite
from privileged_tests import HANDLER
from reference import verify_files


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cross',default='riscv64-elf-')
    args=parser.parse_args()
    suite=NativeSuite(args.cross)
    timings=[(1,0),(5,0),(1,3),(5,7),(20,3)]
    suite.compile('buffer_compressed','''
        li a0,0
        .rept 128
        c.addi a0,1
        .endr
        sd a0,512(zero)
        SIM_EXIT
    ''',compressed=True)
    suite.run('buffer_compressed',signature=128,causes=[],timings=timings)
    assert suite.stats[-1]['fetch_buffer_reuses']>=64

    suite.compile('buffer_mixed','''
        .4byte 0x00000513
        .rept 32
        c.addi a0,1
        .4byte 0x00250513
        c.addi a0,3
        .endr
        sd a0,512(zero)
        SIM_EXIT
    ''',compressed=True)
    suite.run('buffer_mixed',signature=192,causes=[],timings=timings)

    suite.compile('buffer_branch','''
        li a0,9
        sd a0,528(zero)
        c.j target
        sd zero,528(zero)
        c.addi a0,31
    target:
        c.addi a0,7
        sd a0,512(zero)
        SIM_EXIT
    ''',compressed=True)
    suite.run('buffer_branch',signature=16,causes=[],timings=timings)

    suite.compile('buffer_patch','''
        la t0,func
        jalr ra,0(t0)
        li t1,0x451d
        sh t1,0(t0)
        fence.i
        jalr ra,0(t0)
        sd a0,512(zero)
        SIM_EXIT
        .org 0x100
    func:
        .2byte 0x4505
        .2byte 0x8082
    ''',compressed=True)
    suite.run('buffer_patch',signature=7,causes=[],timings=timings)

    for mapped in (True,False):
        boot=f'''
            la t0,handler
            csrw mtvec,t0
            li a0,0
            li t0,{(8<<60)|6:#x}
            csrw satp,t0
            li t0,0x800
            csrw mstatus,t0
            li t0,0x40000ffc
            csrw mepc,t0
            mret
        '''
        data=HANDLER+f'''
            .org 0x1ffc
            .2byte 0x0001
            .2byte 0x0513
            .org 0x3000
            .2byte 0x02a0
            .4byte 0x73
            .org 0x6000
            .dword 0,0x1c01
            .org 0x7000
            .dword 0x2001
            .org 0x8000
            .dword 0x44b,{0xc4b if mapped else 0:#x}
        '''
        name=f'buffer_cross_page_{int(mapped)}';suite.compile(name,boot,data)
        for records,ram in suite.run(name,signature=42 if mapped else 0,causes=[9 if mapped else 12],timings=timings):
            trap=next(r for r in records if r['kind']=='trap')
            assert trap['pc']==(0x40001002 if mapped else 0x40000ffe),trap
            assert trap['value']==(0 if mapped else 0x40001000),trap

    # MRET straddles a word; its following halfword has the same VA as mepc.
    # Returning to U must discard it and recheck the mapping's missing U bit.
    suite.compile('buffer_privilege','''
        la t0,handler
        csrw mtvec,t0
        li a0,0
        li t0,0x8000000000000006
        csrw satp,t0
        csrw mstatus,zero
        li t0,0x1006
        csrw mepc,t0
        li t0,0x1002
        jalr zero,0(t0)
    ''',HANDLER+'''
        .org 0x1002
        .4byte 0x30200073
        .2byte 0x4505
        .org 0x6000
        .dword 0x1c01
        .org 0x7000
        .dword 0x2001
        .org 0x8000
        .dword 0,0x44b
    ''')
    for records,ram in suite.run('buffer_privilege',signature=0,causes=[12],timings=timings):
        trap=next(r for r in records if r['kind']=='trap')
        assert trap['pc']==trap['value']==0x1006,trap

    suite.compile('buffer_illegal','''
        li a0,55
        sd a0,528(zero)
        la t0,handler
        csrw mtvec,t0
        .balign 4
        c.nop
        .2byte 0
        sd zero,528(zero)
    handler:
        sd a0,512(zero)
        SIM_EXIT
    ''',compressed=True)
    suite.run('buffer_illegal',signature=55,causes=[2],timings=timings)

    ablation=[]
    for name,expected in [('buffer_compressed',128),('buffer_mixed',192)]:
        for latency,gap in [(1,0),(5,0),(5,3)]:
            pair=[]
            for mode,sim in [('enabled',suite.simulator),('disabled','build/nobuffer_obj/Vrv64_core')]:
                trace=f'build/{name}-{mode}-l{latency}-g{gap}.trace.jsonl'
                r=subprocess.run([sim,f'build/{name}.bin',str(latency),'-',str(gap),trace],
                                 capture_output=True,text=True,check=True)
                stats=json.loads(r.stdout)
                count=verify_files(f'build/{name}.bin',trace)
                assert stats['result']==expected and stats['instret']==count
                pair.append(stats)
                ablation.append(dict(program=name,mode=mode,latency=latency,gap=gap,**stats))
            on,off=pair
            assert on['instret']==off['instret'] and on['cycles']<off['cycles'],pair
            assert on['fetch_buffer_reuses']>0 and off['fetch_buffer_reuses']==0,pair
    with Path('build/fetch-buffer-ablation.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(ablation[0]),lineterminator='\n')
        writer.writeheader();writer.writerows(ablation)
    Path('build/fetch-buffer-stats.json').write_text(json.dumps(suite.stats,indent=2)+'\n')
    subprocess.run([suite.simulator,'build/buffer_compressed.bin','1','build/fetch-buffer.vcd','0'],
                   capture_output=True,text=True,check=True)
    print(f'FETCH BUFFER PASS: {suite.runs} runs, {suite.commits} commits, {suite.traps} traps; 12 buffer-on/off runs checked')


if __name__=='__main__':main()
