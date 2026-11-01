"""Pipeline hazards, killed fetch faults, precise traps and instruction visibility."""
import argparse
import json
import subprocess
from pathlib import Path
from native_test_support import NativeSuite,words


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cross',default='riscv64-elf-')
    args=parser.parse_args()
    suite=NativeSuite(args.cross)
    timings=[(1,0),(5,0),(1,3),(5,7),(20,3)]
    suite.compile('pipeline_bypass','''
        li a0,7
        li a1,6
        mul a2,a0,a1
        add a3,a2,a2
        sd a3,512(zero)
        ld a4,512(zero)
        add a5,a4,a0
        sd a5,520(zero)
        addi zero,a5,1
        add a0,zero,a0
        sd a0,528(zero)
        li a1,91
        bne a5,a1,bad
        SIM_EXIT
    bad:
        .word 0
    ''',compressed=True)
    for _,ram in suite.run('pipeline_bypass',signature=84,causes=[],timings=timings):
        assert words(ram,512,3)==[84,91,7]

    suite.compile('pipeline_kill','''
        li a0,1
        beq a0,a0,target
        sd a0,528(zero)
        .word 0
    target:
        la a1,edge
        jalr zero,0(a1)
    finish:
        li a0,123
        sd a0,512(zero)
        SIM_EXIT
        .org 0xfffc
    edge:
        jal zero,finish
    ''')
    suite.run('pipeline_kill',signature=123,causes=[],timings=timings)

    suite.compile('pipeline_precise','''
        la t0,handler
        csrw mtvec,t0
        li a0,55
        sd a0,528(zero)
        .word 0
        sd zero,528(zero)
    handler:
        sd a0,512(zero)
        csrr t0,mepc
        sd t0,520(zero)
        SIM_EXIT
    ''')
    suite.run('pipeline_precise',signature=55,causes=[2],timings=timings)

    # Patch the following ADDI, then discard any pre-fetched old instruction.
    suite.compile('pipeline_fence_i','''
        la a0,patched
        li a1,0x02a00613
        sw a1,0(a0)
        fence.i
    patched:
        addi a2,zero,1
        sd a2,512(zero)
        SIM_EXIT
    ''')
    suite.run('pipeline_fence_i',signature=42,causes=[],timings=timings)

    # The first counter read must include the preceding instruction's retirement.
    suite.compile('pipeline_csr_order','''
        li a0,1
        csrr a1,minstret
        addi a0,a0,1
        csrr a2,minstret
        sub a3,a2,a1
        sd a3,512(zero)
        SIM_EXIT
    ''',compressed=True)
    suite.run('pipeline_csr_order',signature=2,causes=[],timings=timings)

    result=subprocess.run([suite.simulator,'build/pipeline_bypass.bin','1','build/pipeline.vcd','0'],
                          check=True,capture_output=True,text=True)
    stats=json.loads(result.stdout)
    assert stats['overlap_cycles']>0,stats
    assert stats['xw_overlap_cycles']>0,stats
    assert stats['bypass_count']>0,stats
    # At the host's exit-store commit, younger instructions can still be in flight.
    assert stats['issue_count']>=stats['instret'],stats
    Path('build/pipeline-stats.json').write_text(json.dumps(stats,indent=2)+'\n')
    print(f'PIPELINE PASS: {suite.runs} runs, {suite.commits} commits; overlap={stats["overlap_cycles"]}, bypass={stats["bypass_count"]}; trace=build/pipeline.vcd')


if __name__=='__main__': main()
