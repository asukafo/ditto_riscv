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

VERSIONS=('v1_multicycle','v2_single_issue')
PROGRAMS={'sum':2080,'dependency':128,'pointer_chase':2016,'load_add_store':14,
          'bit_ops':0x7ffffffffffffffc,'c_demo':1488,'full_demo':949,
          'independent':640,'compressed':128}
TIMINGS=((1,0),(5,0),(5,3))


def write_csv(path,rows):
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n')
        writer.writeheader();writer.writerows(rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id',default=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    parser.add_argument('--cross',default='riscv64-elf-')
    args=parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+',args.run_id):parser.error('invalid run id')
    destination=ROOT/'results'/'comparisons'/args.run_id
    try:
        destination.mkdir(parents=True,exist_ok=False)
    except FileExistsError:
        parser.error('run-id already exists; choose a new id to preserve previous measurements')
    all_rows=[];images={}
    for version in VERSIONS:
        folder=ROOT/'versions'/version
        results=folder/'results'/args.run_id
        results.mkdir(parents=True,exist_ok=False)
        targets=['build/full_obj/Vrv64_core']+[f'build/{name}.bin' for name in PROGRAMS if name not in ('independent','compressed')]+['timing']
        with (results/'build.log').open('w') as log:
            subprocess.run(['make',*targets,f'CROSS={args.cross}'],cwd=folder,stdout=log,stderr=subprocess.STDOUT,check=True)
        for name in ('independent','compressed'):
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
        rows=[]
        for name,expected in PROGRAMS.items():
            image=folder/'build'/f'{name}.bin'
            digest=hashlib.sha256(image.read_bytes()).hexdigest()
            manifest['images'][name]=digest
            if name in images: assert images[name]==digest,(version,name,'different program binary')
            images[name]=digest
            for latency,gap in TIMINGS:
                # Raw traces remain under each version's ignored build directory.
                trace=folder/'build'/f'benchmark-{args.run_id}-{name}-l{latency}-g{gap}.trace.jsonl'
                run=subprocess.run([str(folder/'build/full_obj/Vrv64_core'),str(image),str(latency),'-',str(gap),str(trace)],
                                   cwd=folder,capture_output=True,text=True,check=True)
                stats=json.loads(run.stdout)
                assert stats['result']==expected,(version,name,stats)
                count=verify_files(image,trace)
                assert count==stats['instret']
                row={'version':version,'program':name,'latency':latency,'gap':gap,
                     'cycles':stats['cycles'],'instret':stats['instret'],'cpi':round(stats['cycles']/count,6),
                     'period_ns':period,'estimated_time_ns':round(stats['cycles']*period,3),
                     'area_library_units':area,'requests':stats['requests'],
                     'overlap_cycles':stats.get('overlap_cycles',0),'xw_overlap_cycles':stats.get('xw_overlap_cycles',0),
                     'bypass_count':stats.get('bypass_count',0)}
                rows.append(row)
        write_csv(results/'performance.csv',rows)
        (results/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        all_rows+=rows
        print(f'{version}: {len(rows)} checked runs, period={period} ns, area={area}',flush=True)
    write_csv(destination/'comparison.csv',all_rows)
    first={(r['program'],r['latency'],r['gap']):r for r in all_rows if r['version']==VERSIONS[0]}
    for row in all_rows:
        if row['version']==VERSIONS[1]:
            assert row['instret']==first[(row['program'],row['latency'],row['gap'])]['instret']
    (destination/'README.md').write_text('Generated by `python3 tools/benchmark.py`.\n\n'
        'Both versions execute byte-identical programs. All commits and final RAM checked against the independent model.\n'
        'Timing is pre-layout Nangate45 typical with ideal clocks; estimated_time_ns is a model estimate, not measured hardware time.\n')
    print(destination,flush=True)


if __name__=='__main__':main()
