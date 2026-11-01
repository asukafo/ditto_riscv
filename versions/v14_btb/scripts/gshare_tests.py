"""Committed-history integration, saved lookup-index audit and bimodal ablation."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
from native_test_support import NativeSuite
from reference import verify_files
from waveforms import read_vcd,value_at


def audit(path):
    s=read_vcd(path);history=0;valid=[False]*32;counters=[1]*32;queue=[];queries=trains=stale=clears=0;query=None
    fields=('global_history','retire','wb_serial','trap_enter','bht_train_event','wb_branch_taken',
            'wb_predicted_index','wb_pc','issue_fire','fe_pc','fe_predicted_index','fe_valid','redirect','btb_lookup_event','unused_fe_query_pc')
    for t,v in s['clk']:
        if v!=1 or value_at(s['reset'],t,True):continue
        pre={k:value_at(s[k],t,True) for k in fields}
        assert pre['global_history']==history
        if pre['retire']:
            pc,index=queue.pop(0);assert pc==pre['wb_pc'] and index==pre['wb_predicted_index'],(pc,index,pre)
        if pre['issue_fire']:queue.append((pre['fe_pc'],pre['fe_predicted_index']))
        if pre['btb_lookup_event']:
            qi=((pre['unused_fe_query_pc']>>1)&31)^history
            query=dict(pc=pre['unused_fe_query_pc'],index=qi,hit=valid[qi],taken=counters[qi]>=2)
        # A newly registered packet used pre-edge history/table, including simultaneous training.
        if value_at(s['fe_valid'],t) and (not pre['fe_valid'] or pre['issue_fire']):
            pc=value_at(s['fe_pc'],t);early=value_at(s['fe_predicted_btb'],t) and value_at(s['fe_insn'],t)&127!=0x63
            if early:assert query is not None and query['pc']==pc
            index=query['index'] if early else ((pc>>1)&31)^history
            assert value_at(s['fe_predicted_index'],t)==index,(t,pc,index)
            insn=value_at(s['fe_insn'],t);size=value_at(s['fe_bytes'],t)
            if insn&127==0x63:
                offset=((insn>>31)<<12)|(((insn>>7)&1)<<11)|(((insn>>25)&63)<<5)|(((insn>>8)&15)<<1)
                if offset&4096:offset-=8192
                hit=query['hit'] if early else valid[index]
                taken=(query['taken'] if early else counters[index]>=2) if hit else offset<0
                target=(pc+offset if taken else pc+size)&((1<<64)-1)
                assert value_at(s['fe_predicted_next'],t)==target,(t,pc,index,target)
                assert value_at(s['fe_predicted_dynamic'],t)==hit
            queries+=1
        if pre['trap_enter'] or (pre['retire'] and pre['wb_serial']):
            history=0;valid=[False]*32;counters=[1]*32;clears+=1
        elif pre['bht_train_event']:
            index=pre['wb_predicted_index'];taken=pre['wb_branch_taken']
            stale+=index!=(((pre['wb_pc']>>1)&31)^history)
            counters[index]=(2 if taken else 1) if not valid[index] else min(3,counters[index]+1) if taken else max(0,counters[index]-1)
            valid[index]=True;history=((history<<1)|taken)&15;trains+=1
        assert value_at(s['global_history'],t)==history,(t,history)
    assert queries>10 and trains>10,(queries,trains,stale)
    return dict(queries=queries,trains=trains,saved_index_differs_from_retirement_recompute=stale,clears=clears)


def main():
    p=argparse.ArgumentParser();p.add_argument('--cross',default='riscv64-elf-');args=p.parse_args()
    suite=NativeSuite(args.cross);timings=[(1,0),(5,0),(1,3),(5,7),(20,3)]
    finish='sd a0,512(zero)\nSIM_EXIT\n'
    bodies={
        'alternating':('''li s0,64
        li a0,0
    1:  andi t0,s0,1
        bnez t0,2f
        addi a0,a0,1
    2:  addi a0,a0,1
        addi s0,s0,-1
        bnez s0,1b
    ''',96,False),
        'correlated':('''li s0,64
        li a0,0
    1:  andi t0,s0,1
        beqz t0,2f
        addi a0,a0,1
    2:  beqz t0,3f
        addi a0,a0,1
    3:  addi s0,s0,-1
        bnez s0,1b
    ''',64,False),
        'adjacent':('''li s0,32
        li a0,0
    1:  beq zero,zero,2f
    2:  bne zero,zero,dead
        blt zero,zero,dead
        bge zero,zero,3f
        .word 0
    3:  addi a0,a0,1
        addi s0,s0,-1
        bnez s0,1b
    ''',32,False),
        'serial':('''li s0,8
        li a0,0
    1:  beq zero,zero,2f
        .word 0
    2:  fence.i
        addi a0,a0,1
        addi s0,s0,-1
        bnez s0,1b
    ''',8,False),
        'compressed_adjacent':('''li s0,32
        li s1,0
        li a0,0
        .balign 4
    1:  c.beqz s1,2f
    2:  c.bnez s1,dead
        c.addi a0,1
        c.addi s0,-1
        c.bnez s0,1b
    ''',32,True),
        'compressed':('''li s0,32
        li a0,0
    1:  andi s1,s0,1
        c.beqz s1,2f
        c.addi a0,1
    2:  c.addi s0,-1
        c.bnez s0,1b
    ''',16,True),
    }
    for name,(body,signature,compressed) in bodies.items():
        case='gshare_'+name;suite.compile(case,body+finish+'dead: .word 0\n',compressed=compressed)
        results=suite.run(case,signature=signature,causes=[],timings=timings)
        for (records,_),stats in zip(results,suite.stats[-5:]):
            branches=sum(r['kind']=='commit' and ((r['insn']&127)==0x63 or (compressed and r['bytes']==2 and (r['insn']&0xe003) in (0xc001,0xe001))) for r in records)
            assert stats['gshare_enabled']==1 and stats['bht_trains']==branches
    rows=[]
    for name in bodies:
        for latency,gap in [(1,0),(5,0),(5,3)]:
            pair=[]
            for mode,sim in [('gshare',suite.simulator),('bimodal','build/bimodal_obj/Vrv64_core')]:
                trace=f'build/gshare-{name}-{mode}-l{latency}-g{gap}.trace.jsonl'
                stats=json.loads(subprocess.check_output([sim,f'build/gshare_{name}.bin',str(latency),'-',str(gap),trace],text=True))
                assert verify_files(f'build/gshare_{name}.bin',trace)==stats['instret'];pair.append(stats)
            on,off=pair;assert off['gshare_enabled']==0 and off['bht_enabled']==1
            assert on['result']==off['result'] and on['instret']==off['instret']
            rows.append(dict(program=name,latency=latency,gap=gap,gshare_cycles=on['cycles'],bimodal_cycles=off['cycles'],gshare_misses=on['conditional_misses'],bimodal_misses=off['conditional_misses']))
    with Path('build/gshare-ablation.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    audits={}
    for name in ('alternating','adjacent','compressed_adjacent','serial'):
        wave=f'build/gshare-{name}.vcd'
        subprocess.run([suite.simulator,f'build/gshare_{name}.bin','5',wave,'3'],check=True,capture_output=True,text=True)
        audits[name]=audit(wave)
    assert audits['serial']['clears']>0
    assert sum(x['saved_index_differs_from_retirement_recompute'] for x in audits.values())>0
    Path('build/gshare-index-audit.json').write_text(json.dumps(audits,indent=2)+'\n')
    Path('build/gshare-native-stats.json').write_text(json.dumps(suite.stats,indent=2)+'\n')
    print(f'GSHARE INTEGRATION PASS: {suite.runs} runs, {suite.commits} commits, {suite.traps} traps; 36 on/off runs; saved-index VCD audit {audits}')


if __name__=='__main__':main()
