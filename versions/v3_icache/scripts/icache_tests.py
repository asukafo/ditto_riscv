"""Cache integration: warm permissions/aliases, FENCE.I, boundaries and on/off comparison."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
from native_test_support import NativeSuite
from reference import verify_files


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cross',default='riscv64-elf-')
    args=parser.parse_args()
    suite=NativeSuite(args.cross)
    timings=[(1,0),(5,0),(1,3),(5,7),(20,3)]
    suite.compile('cache_boundary','''
        c.j target
        .org 14
    target:
        .4byte 0x02a00513
        sd a0,512(zero)
        SIM_EXIT
    ''',compressed=True)
    suite.run('cache_boundary',signature=42,causes=[],timings=timings)

    suite.compile('cache_hot_patch','''
        la t0,func
        jalr ra,0(t0)
        li t1,0x02a00513
        sw t1,0(t0)
        fence.i
        jalr ra,0(t0)
        sd a0,512(zero)
        SIM_EXIT
        .org 0x100
    func:
        addi a0,zero,1
        ret
    ''')
    suite.run('cache_hot_patch',signature=42,causes=[],timings=timings)
    assert suite.stats[-1]['icache_invalidations']==1

    for name,priv,ppn,cause,signature in [('warm_user_denied',0,1,12,42),
                                        ('warm_physical_alias',1,1,9,42),
                                        ('warm_distinct_physical_tag',1,2,9,99)]:
        boot=f'''
            la t0,handler
            csrw mtvec,t0
            li a1,0
            jal ra,warm
            li a1,1
            li t0,{(8<<60)|6:#x}
            csrw satp,t0
            li t0,{priv<<11:#x}
            csrw mstatus,t0
            li t0,0x40000000
            csrw mepc,t0
            mret
        '''
        data=f'''
            .org 0x800
        handler:
            sd a0,512(zero)
            SIM_EXIT
            .org 0x1000
        warm:
            li a0,42
            bnez a1,1f
            ret
        1:  ecall
            .org 0x2000
            li a0,99
            ecall
            .org 0x6000
            .dword 0,0x1c01
            .org 0x7000
            .dword 0x2001
            .org 0x8000
            .dword {(ppn<<10)|0x4b:#x}
        '''
        suite.compile(name,boot,data)
        suite.run(name,signature=signature,causes=[cause],timings=timings)
        assert suite.stats[-1]['icache_hits']>0

    suite.compile('cache_loop','''
        li t0,64
        li a0,0
    1:  addi a0,a0,1
        addi t0,t0,-1
        bnez t0,1b
        sd a0,512(zero)
        SIM_EXIT
    ''',compressed=True)
    suite.run('cache_loop',signature=64,causes=[],timings=timings)

    # Same v3 front end and program, only the cache-enable parameter differs.
    ablation=[]
    for latency,gap in [(1,0),(5,0),(5,3)]:
        pair=[]
        for mode,sim in [('enabled',suite.simulator),('disabled','build/noicache_obj/Vrv64_core')]:
            trace=f'build/cache-loop-{mode}-l{latency}-g{gap}.trace.jsonl'
            process=subprocess.run([sim,'build/cache_loop.bin',str(latency),'-',str(gap),trace],
                                   check=True,capture_output=True,text=True)
            stats=json.loads(process.stdout)
            assert stats['result']==64
            assert verify_files('build/cache_loop.bin',trace)==stats['instret']
            pair.append(stats)
            ablation.append(dict(mode=mode,latency=latency,gap=gap,**stats))
        on,off=pair
        assert on['requests']<off['requests'],pair
        assert on['icache_hits']>on['icache_misses'] and off['icache_hits']==off['icache_misses']==0,pair
        assert on['instret']==off['instret'],pair
        if latency>=5: assert on['cycles']<off['cycles'],pair
    with Path('build/icache-ablation.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(ablation[0]),lineterminator='\n')
        writer.writeheader();writer.writerows(ablation)
    Path('build/icache-native-stats.json').write_text(json.dumps(suite.stats,indent=2)+'\n')
    # This VCD explicitly contains a cold refill followed by warm loop hits.
    subprocess.run([suite.simulator,'build/cache_loop.bin','5','build/icache.vcd','3'],check=True,capture_output=True,text=True)
    print(f'ICACHE INTEGRATION PASS: {suite.runs} runs, {suite.commits} commits, {suite.traps} traps; 6 cache-on/off runs checked')


if __name__=='__main__':main()
