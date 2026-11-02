"""Fetch decoupling, full-queue recovery and precise instruction visibility."""
import argparse
from collections import deque
import csv
import json
from pathlib import Path
import subprocess
from native_test_support import NativeSuite,words
from reference import verify_files
from waveforms import read_vcd,value_at


def audit(path):
    s=read_vcd(path);queue=deque();inflight=0;peak=flushes=busy=exchanges=0
    fields=('pc','predicted_next','cause','value','insn','raw','bytes','illegal','fault','predicted_return','predicted_dynamic','predicted_btb','predicted_index')
    for t,v in s['clk']:
        if v!=1 or value_at(s['reset'],t,True):continue
        pre=lambda name:value_at(s[name],t,True)
        assert pre('fetch_queue_occupancy')==len(queue)
        raw=tuple(pre('raw_fe_'+f) for f in fields)
        flush=pre('fetch_redirect');valid=pre('raw_fe_valid');ready=pre('fe_ready')
        ur=not flush and (len(queue)<4 or ready);dv=not flush and (bool(queue) or valid)
        assert pre('raw_fe_ready')==ur and pre('fe_valid')==dv
        if dv:assert tuple(pre('fe_'+f) for f in fields)==(queue[0] if queue else raw)
        push=valid and ur and not (not queue and ready);pop=not flush and bool(queue) and ready
        assert pre('fetch_queue_push_event')==push and pre('fetch_queue_pop_event')==pop
        peak=max(peak,len(queue));busy+=push and pre('state')!=0 and not pre('ex_finish')
        exchanges+=len(queue)==4 and push and pop
        if flush:
            flushes+=bool(queue);queue.clear()
        else:
            if pop:queue.popleft()
            if push:queue.append(raw)
        assert value_at(s['fetch_queue_occupancy'],t)==len(queue)
        if pre('f_rsp_valid') and pre('f_rsp_ready'):inflight-=1
        if pre('f_valid') and pre('f_ready'):inflight+=1
        assert 0<=inflight<=1,('multiple outstanding fetches',t,inflight)
    return dict(peak=peak,nonempty_flushes=flushes,fill_while_x_busy=busy,full_pop_push=exchanges,max_outstanding_fetches=1)


def main():
    p=argparse.ArgumentParser();p.add_argument('--cross',default='riscv64-elf-');args=p.parse_args()
    suite=NativeSuite(args.cross);timings=[(1,0),(5,0),(1,3),(5,7),(20,3)]
    finish='sd a0,512(zero)\nSIM_EXIT\n'
    cases={
      'divide':('''li s0,4
        li a0,0
        li a1,1000
        li a2,7
    1:  div t0,a1,a2
        .rept 12
        addi a0,a0,1
        .endr
        addi s0,s0,-1
        bnez s0,1b
        sd t0,520(zero)
    '''+finish,48,False,[]),
      'loads':('''li s0,8
        li a0,0
        li s1,0x3000
    1:  ld t0,0(s1)
        .rept 12
        addi a0,a0,1
        .endr
        addi s1,s1,16
        addi s0,s0,-1
        bnez s0,1b
    '''+finish+'''.org 0x3000
        .rept 16
        .dword 7
        .endr
    ''',96,False,[]),
      'flush':('''li a0,0
        li t0,64
        li t1,2
        div t2,t0,t1
        bnez t2,target
        sd t0,528(zero)
        .word 0
        addi a0,a0,100
    target:
        li a0,42
    '''+finish,42,False,[]),
      'precise':('''la t0,handler
        csrw mtvec,t0
        li t0,64
        li t1,2
        div t2,t0,t1
        li a0,55
        .word 0
        sd zero,512(zero)
        SIM_EXIT
    handler:
    '''+finish,55,False,[2]),
      'fence_i':('''la t0,patched
        li t1,0x02a00513
        li a1,1000
        li a2,7
        div t2,a1,a2
        sw t1,0(t0)
        fence.i
    patched:
        addi a0,zero,1
    '''+finish,42,False,[]),
      'compressed':('''li s0,4
        li a0,0
        li a1,1000
        li a2,7
    1:  div t0,a1,a2
        c.nop
        .4byte 0x00150513
        .rept 9
        c.addi a0,1
        .endr
        c.addi s0,-1
        c.bnez s0,1b
    '''+finish,40,True,[]),
    }
    for name,(body,signature,compressed,causes) in cases.items():
        suite.compile('queue_'+name,body,compressed=compressed)
        results=suite.run('queue_'+name,signature=signature,causes=causes,timings=timings)
        for (_,ram),stats in zip(results,suite.stats[-5:]):
            assert stats['fetch_queue_enabled']==1 and stats['fetch_queue_peak']<=4
            if name=='divide':assert words(ram,520,1)==[142]
            if name=='flush':assert words(ram,528,1)==[0]
    rows=[]
    for name in cases:
        for latency,gap in [(1,0),(5,0),(5,3)]:
            pair=[]
            for mode,sim in [('queue',suite.simulator),('disabled','build/noqueue_obj/Vrv64_core')]:
                trace=f'build/queue-{name}-{mode}-l{latency}-g{gap}.trace.jsonl'
                stats=json.loads(subprocess.check_output([sim,f'build/queue_{name}.bin',str(latency),'-',str(gap),trace],text=True))
                assert verify_files(f'build/queue_{name}.bin',trace)==stats['instret'];pair.append(stats)
            on,off=pair;assert on['result']==off['result'] and on['instret']==off['instret']
            assert off['fetch_queue_enabled']==off['fetch_queue_pushes']==off['fetch_queue_peak']==0
            if name=='divide':assert on['cycles']<off['cycles'] and on['fetch_queue_peak']==4 and on['fetch_queue_fill_while_x_busy']>0
            rows.append(dict(program=name,latency=latency,gap=gap,queue_cycles=on['cycles'],disabled_cycles=off['cycles'],queue_peak=on['fetch_queue_peak'],queue_full_cycles=on['fetch_queue_full_cycles'],queue_flushed_packets=on['fetch_queue_flushed_packets']))
    with Path('build/fetch-queue-ablation.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    audits={}
    for name in ('divide','flush','precise','fence_i','compressed'):
        wave=f'build/queue-{name}.vcd'
        subprocess.run([suite.simulator,f'build/queue_{name}.bin','5',wave,'3'],check=True,capture_output=True,text=True)
        audits[name]=audit(wave)
    assert audits['divide']['peak']==4 and audits['divide']['fill_while_x_busy']>0
    assert audits['flush']['nonempty_flushes']>0 and audits['fence_i']['nonempty_flushes']>0
    Path('build/fetch-queue-audit.json').write_text(json.dumps(audits,indent=2)+'\n')
    Path('build/fetch-queue-native-stats.json').write_text(json.dumps(suite.stats,indent=2)+'\n')
    print(f'FETCH QUEUE INTEGRATION PASS: {suite.runs} runs, {suite.commits} commits, {suite.traps} traps; 36 on/off runs; packet/inflight VCD audit {audits}')


if __name__=='__main__':main()
