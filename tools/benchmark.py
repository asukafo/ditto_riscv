"""Compare frozen versions; every run creates new, non-overwriting result directories."""
import argparse
import csv
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'versions'/'v1_multicycle'/'scripts'))
from reference import verify_files
from profile_stalls import profile

VERSIONS=('v1_multicycle','v2_single_issue','v3_icache','v4_fetch_buffer','v5_early_restart','v6_dcache','v7_dcache_early','v8_split_memory')
PROGRAMS={'sum':2080,'dependency':128,'pointer_chase':2016,'load_add_store':14,
          'bit_ops':0x7ffffffffffffffc,'c_demo':1488,'full_demo':949,
          'independent':640,'compressed':128,'data_reuse':896}
TIMINGS=((1,0),(5,0),(5,3))


def write_csv(path,rows):
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n')
        writer.writeheader();writer.writerows(rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id',default=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    parser.add_argument('--cross',default='riscv64-elf-')
    parser.add_argument('--versions',nargs='+',choices=VERSIONS,default=list(VERSIONS))
    args=parser.parse_args()
    if len(set(args.versions))!=len(args.versions):parser.error('duplicate version')
    if not re.fullmatch(r'[A-Za-z0-9_-]+',args.run_id):parser.error('invalid run id')
    destination=ROOT/'results'/'comparisons'/args.run_id
    try:
        destination.mkdir(parents=True,exist_ok=False)
    except FileExistsError:
        parser.error('run-id already exists; choose a new id to preserve previous measurements')
    all_rows=[];images={}
    for version in args.versions:
        folder=ROOT/'versions'/version
        results=folder/'results'/args.run_id
        results.mkdir(parents=True,exist_ok=False)
        targets=['build/full_obj/Vrv64_core']+[f'build/{name}.bin' for name in PROGRAMS if name not in ('independent','compressed','data_reuse')]+['timing']
        if version in ('v3_icache','v4_fetch_buffer','v5_early_restart','v6_dcache','v7_dcache_early','v8_split_memory'):targets.append('build/noicache_obj/Vrv64_core')
        if version in ('v4_fetch_buffer','v5_early_restart','v6_dcache','v7_dcache_early','v8_split_memory'):targets.append('build/nobuffer_obj/Vrv64_core')
        if version in ('v5_early_restart','v6_dcache','v7_dcache_early','v8_split_memory'):targets.append('build/noearly_obj/Vrv64_core')
        if version in ('v6_dcache','v7_dcache_early','v8_split_memory'):targets.append('build/nodcache_obj/Vrv64_core')
        if version in ('v7_dcache_early','v8_split_memory'):targets.append('build/nodataearly_obj/Vrv64_core')
        if version=='v8_split_memory':targets.append('build/unsplit_obj/Vrv64_core')
        with (results/'build.log').open('w') as log:
            subprocess.run(['make',*targets,f'CROSS={args.cross}'],cwd=folder,stdout=log,stderr=subprocess.STDOUT,check=True)
        for name in ('independent','compressed','data_reuse'):
            subprocess.run([args.cross+'gcc','-march=rv64imac_zicsr_zifencei','-mabi=lp64','-nostdlib','-nostartfiles',
                            '-Wl,-Ttext=0,-e,_start,--no-relax','-o',f'build/{name}.elf',str(ROOT/'benchmarks'/f'{name}.S')],cwd=folder,check=True)
            subprocess.run([args.cross+'objcopy','-O','binary','-j','.text',f'build/{name}.elf',f'build/{name}.bin'],cwd=folder,check=True)
        timing=(folder/'build/timing.log').read_text()
        mapping=(folder/'build/mapping.log').read_text()
        period=float(re.search(r'period_min = ([\d.]+)',timing)[1])
        area=float(re.search(r"Chip area for top module.*?: ([\d.]+)",mapping)[1])
        (results/'timing-report.txt').write_text('\n'.join(line.rstrip() for line in timing.splitlines())+'\n')
        summary=mapping[mapping.rfind('=== design hierarchy ==='):]
        (results/'mapping-summary.txt').write_text('\n'.join(line.rstrip() for line in summary.splitlines())+'\n')
        manifest={'version':version,'run_id':args.run_id,'version_metadata':json.loads((folder/'version.json').read_text()),
                  'rtl_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((folder/'rtl').glob('*.sv'))},
                  'period_ns':period,'area_library_units':area,'mapping_sha256':hashlib.sha256(mapping.encode()).hexdigest(),
                  'images':{},'tools':{}}
        for tool in (['verilator','--version'],['yosys','-V'],[args.cross+'gcc','--version']):
            manifest['tools'][tool[0]]=subprocess.check_output(tool,text=True).splitlines()[0]
        rows=[];ablations=[];buffer_ablations=[];early_ablations=[];data_ablations=[];data_early_ablations=[];split_ablations=[]
        for name,expected in PROGRAMS.items():
            image=folder/'build'/f'{name}.bin'
            digest=hashlib.sha256(image.read_bytes()).hexdigest()
            manifest['images'][name]=digest
            if name in images: assert images[name]==digest,(version,name,'different program binary')
            images[name]=digest
            for latency,gap in TIMINGS:
                # Raw traces remain under each version's ignored build directory.
                trace=folder/'build'/f'benchmark-{args.run_id}-{name}-l{latency}-g{gap}.trace.jsonl'
                capture_profile=version in ('v2_single_issue','v3_icache','v4_fetch_buffer','v5_early_restart','v6_dcache','v7_dcache_early','v8_split_memory') and name=='sum' and (latency,gap)==(5,3)
                wave=folder/'build'/f'benchmark-{args.run_id}-stall-profile.vcd' if capture_profile else '-'
                run=subprocess.run([str(folder/'build/full_obj/Vrv64_core'),str(image),str(latency),str(wave),str(gap),str(trace)],
                                   cwd=folder,capture_output=True,text=True,check=True)
                stats=json.loads(run.stdout)
                assert stats['result']==expected,(version,name,stats)
                count=verify_files(image,trace)
                assert count==stats['instret']
                if capture_profile:
                    observed=profile(wave)
                    assert observed['sampled_cycles']==stats['cycles'],observed
                    for key,value in observed.items():
                        if key in stats:assert stats[key]==value,(key,stats[key],value)
                    stats.update(observed)
                    (results/'stall-profile.json').write_text(json.dumps(observed,indent=2)+'\n')
                row={'version':version,'program':name,'latency':latency,'gap':gap,
                     'cycles':stats['cycles'],'instret':stats['instret'],'cpi':round(stats['cycles']/count,6),
                     'period_ns':period,'estimated_time_ns':round(stats['cycles']*period,3),
                     'area_library_units':area,'requests':stats['requests'],
                     'overlap_cycles':stats.get('overlap_cycles',0),'xw_overlap_cycles':stats.get('xw_overlap_cycles',0),
                     'bypass_count':stats.get('bypass_count',0)}
                for key in ('icache_hits','icache_misses','icache_refill_requests','icache_miss_wait','icache_invalidations'):
                    row[key]=stats.get(key,0)
                for key in ('data_wait','fetch_wait','reads','writes','dcache_hits','dcache_misses','dcache_refill_requests','dcache_miss_wait','dcache_writes','dcache_bypasses'):
                    row[key]=stats.get(key,0)
                for key in ('instruction_hits_during_data_fill','data_hits_during_instruction_fill'):
                    row[key]=stats.get(key,0)
                for key in ('fetch_buffer_reuses','fetch_buffer_flushes'):
                    row[key]=stats.get(key,0)
                for key in ('frontend_starved_cycles','data_blocked_by_fetch_cycles',
                            'fetch_blocked_by_data_cycles','discarded_fetch_responses'):
                    row[key]=stats.get(key,'')
                rows.append(row)
                if version in ('v3_icache','v4_fetch_buffer','v5_early_restart','v6_dcache','v7_dcache_early','v8_split_memory'):
                    off_trace=folder/'build'/f'benchmark-{args.run_id}-{name}-off-l{latency}-g{gap}.trace.jsonl'
                    off_run=subprocess.run([str(folder/'build/noicache_obj/Vrv64_core'),str(image),str(latency),'-',str(gap),str(off_trace)],
                                           cwd=folder,capture_output=True,text=True,check=True)
                    off=json.loads(off_run.stdout)
                    assert off['result']==expected and verify_files(image,off_trace)==count and off['instret']==count
                    assert off['icache_hits']==off['icache_misses']==0
                    ablations.append(dict(program=name,latency=latency,gap=gap,instret=count,
                        cache_cycles=stats['cycles'],disabled_cycles=off['cycles'],cache_requests=stats['requests'],disabled_requests=off['requests'],
                        cache_frontend_starved=stats['frontend_starved_cycles'],disabled_frontend_starved=off['frontend_starved_cycles'],
                        cache_data_fetch_contention=stats['data_blocked_by_fetch_cycles'],disabled_data_fetch_contention=off['data_blocked_by_fetch_cycles']))
                if version in ('v4_fetch_buffer','v5_early_restart','v6_dcache','v7_dcache_early','v8_split_memory'):
                    off_trace=folder/'build'/f'benchmark-{args.run_id}-{name}-buffer-off-l{latency}-g{gap}.trace.jsonl'
                    off_run=subprocess.run([str(folder/'build/nobuffer_obj/Vrv64_core'),str(image),str(latency),'-',str(gap),str(off_trace)],
                                           cwd=folder,capture_output=True,text=True,check=True)
                    off=json.loads(off_run.stdout)
                    assert off['result']==expected and verify_files(image,off_trace)==count and off['instret']==count
                    assert off['fetch_buffer_reuses']==0
                    baseline=next((r for r in all_rows if r['version']=='v3_icache' and
                                   (r['program'],r['latency'],r['gap'])==(name,latency,gap)),None)
                    if baseline and version=='v4_fetch_buffer':
                        assert (off['cycles'],off['requests'])==(baseline['cycles'],baseline['requests']),(name,latency,gap,off,baseline)
                    buffer_ablations.append(dict(program=name,latency=latency,gap=gap,instret=count,
                        buffer_cycles=stats['cycles'],disabled_cycles=off['cycles'],buffer_requests=stats['requests'],disabled_requests=off['requests'],
                        buffer_icache_lookups=stats['icache_hits']+stats['icache_misses'],disabled_icache_lookups=off['icache_hits']+off['icache_misses'],
                        buffer_reuses=stats['fetch_buffer_reuses'],buffer_flushes=stats['fetch_buffer_flushes']))
                if version in ('v5_early_restart','v6_dcache','v7_dcache_early','v8_split_memory'):
                    off_trace=folder/'build'/f'benchmark-{args.run_id}-{name}-early-off-l{latency}-g{gap}.trace.jsonl'
                    off=json.loads(subprocess.check_output([str(folder/'build/noearly_obj/Vrv64_core'),str(image),str(latency),'-',str(gap),str(off_trace)],cwd=folder,text=True))
                    assert off['result']==expected and verify_files(image,off_trace)==count and off['instret']==count
                    baseline=next((r for r in all_rows if r['version']=='v4_fetch_buffer' and
                                   (r['program'],r['latency'],r['gap'])==(name,latency,gap)),None)
                    if baseline and version=='v5_early_restart':assert (off['cycles'],off['requests'])==(baseline['cycles'],baseline['requests']),(name,latency,gap,off,baseline)
                    early_ablations.append(dict(program=name,latency=latency,gap=gap,instret=count,
                        early_cycles=stats['cycles'],disabled_cycles=off['cycles'],early_requests=stats['requests'],disabled_requests=off['requests']))
                if version in ('v6_dcache','v7_dcache_early','v8_split_memory'):
                    off_trace=folder/'build'/f'benchmark-{args.run_id}-{name}-data-off-l{latency}-g{gap}.trace.jsonl'
                    off=json.loads(subprocess.check_output([str(folder/'build/nodcache_obj/Vrv64_core'),str(image),str(latency),'-',str(gap),str(off_trace)],cwd=folder,text=True))
                    assert off['result']==expected and verify_files(image,off_trace)==count and off['instret']==count
                    assert off['dcache_hits']==off['dcache_misses']==0
                    baseline=next((r for r in all_rows if r['version']=='v5_early_restart' and
                                   (r['program'],r['latency'],r['gap'])==(name,latency,gap)),None)
                    if baseline and version in ('v6_dcache','v7_dcache_early'):assert (off['cycles'],off['requests'])==(baseline['cycles'],baseline['requests']),(name,latency,gap,off,baseline)
                    data_ablations.append(dict(program=name,latency=latency,gap=gap,instret=count,
                        cache_cycles=stats['cycles'],disabled_cycles=off['cycles'],cache_requests=stats['requests'],disabled_requests=off['requests'],
                        cache_data_wait=stats['data_wait'],disabled_data_wait=off['data_wait'],hits=stats['dcache_hits'],misses=stats['dcache_misses']))
                if version in ('v7_dcache_early','v8_split_memory'):
                    off_trace=folder/'build'/f'benchmark-{args.run_id}-{name}-data-early-off-l{latency}-g{gap}.trace.jsonl'
                    off=json.loads(subprocess.check_output([str(folder/'build/nodataearly_obj/Vrv64_core'),str(image),str(latency),'-',str(gap),str(off_trace)],cwd=folder,text=True))
                    assert off['result']==expected and verify_files(image,off_trace)==count and off['instret']==count
                    baseline=next((r for r in all_rows if r['version']=='v6_dcache' and
                                   (r['program'],r['latency'],r['gap'])==(name,latency,gap)),None)
                    if baseline and version=='v7_dcache_early':assert (off['cycles'],off['requests'])==(baseline['cycles'],baseline['requests']),(name,latency,gap,off,baseline)
                    data_early_ablations.append(dict(program=name,latency=latency,gap=gap,instret=count,
                        early_cycles=stats['cycles'],disabled_cycles=off['cycles'],early_requests=stats['requests'],disabled_requests=off['requests'],
                        early_data_wait=stats['data_wait'],disabled_data_wait=off['data_wait'],
                        early_frontend_starved=stats['frontend_starved_cycles'],disabled_frontend_starved=off['frontend_starved_cycles']))
                if version=='v8_split_memory':
                    off_trace=folder/'build'/f'benchmark-{args.run_id}-{name}-unsplit-l{latency}-g{gap}.trace.jsonl'
                    off=json.loads(subprocess.check_output([str(folder/'build/unsplit_obj/Vrv64_core'),str(image),str(latency),'-',str(gap),str(off_trace)],cwd=folder,text=True))
                    assert off['result']==expected and verify_files(image,off_trace)==count and off['instret']==count
                    assert off['split_memory_enabled']==0 and off['instruction_hits_during_data_fill']==0
                    baseline=next((r for r in all_rows if r['version']=='v7_dcache_early' and
                                   (r['program'],r['latency'],r['gap'])==(name,latency,gap)),None)
                    if baseline:assert (off['cycles'],off['requests'])==(baseline['cycles'],baseline['requests']),(name,latency,gap,off,baseline)
                    split_ablations.append(dict(program=name,latency=latency,gap=gap,instret=count,
                        split_cycles=stats['cycles'],legacy_cycles=off['cycles'],split_requests=stats['requests'],legacy_requests=off['requests'],
                        split_frontend_starved=stats['frontend_starved_cycles'],legacy_frontend_starved=off['frontend_starved_cycles'],
                        instruction_hits_during_data_fill=stats['instruction_hits_during_data_fill'],
                        data_hits_during_instruction_fill=stats['data_hits_during_instruction_fill']))
        write_csv(results/'performance.csv',rows)
        if split_ablations:write_csv(results/'split-memory-ablation.csv',split_ablations)
        if data_early_ablations:write_csv(results/'dcache-early-ablation.csv',data_early_ablations)
        if data_ablations:write_csv(results/'dcache-ablation.csv',data_ablations)
        if early_ablations:write_csv(results/'early-restart-ablation.csv',early_ablations)
        if ablations:write_csv(results/'icache-ablation.csv',ablations)
        if buffer_ablations:write_csv(results/'fetch-buffer-ablation.csv',buffer_ablations)
        (results/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        all_rows+=rows
        print(f'{version}: {len(rows)} checked runs, period={period} ns, area={area}',flush=True)
    write_csv(destination/'comparison.csv',all_rows)
    first={(r['program'],r['latency'],r['gap']):r for r in all_rows if r['version']==args.versions[0]}
    for row in all_rows:
        if row['version']!=args.versions[0]:
            assert row['instret']==first[(row['program'],row['latency'],row['gap'])]['instret']
    (destination/'README.md').write_text('Generated by `python3 tools/benchmark.py`.\n\n'
        'Selected versions execute byte-identical programs. All commits and final RAM checked against the independent model.\n'
        'Timing is pre-layout Nangate45 typical with ideal clocks; estimated_time_ns is a model estimate, not measured hardware time.\n')
    print(destination,flush=True)


if __name__=='__main__':main()
