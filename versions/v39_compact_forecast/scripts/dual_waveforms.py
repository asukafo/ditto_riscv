"""Actual issue/retirement width: align dual and same-buffer scalar views by PC."""
import csv,hashlib,json,subprocess
from pathlib import Path
from html import escape
from waveforms import read_vcd,value_at
from reference import verify_files
FIELDS=['state','issue_pair_occupancy','fe_pc','p2_pc','second_valid','pair_raw','pair_waw','pair_fire','issue_count','commit_valid','commit_pc','commit_wdata','commit2_valid','commit2_pc','commit2_wdata','instret']
def draw(path,name,anchor=None):
 s=read_vcd(path);edges=[t for t,v in s['clk'] if v==1 and not value_at(s['reset'],t,True)]
 def p(n,t):return value_at(s[n],t,True)
 if anchor is None:
  first=next(i for i,t in enumerate(edges) if p('pair_fire',t) and p('fe_insn',t)&127==0x13 and (p('fe_insn',t)>>20)&4095 and (p('p2_insn',t)>>20)&4095);anchor=p('fe_pc',edges[first])
 else:first=next(i for i,t in enumerate(edges) if p('issue_fire',t) and p('fe_pc',t)==anchor)
 rows=[]
 for i in range(max(0,first-3),min(len(edges),first+10)):
  t=edges[i];r={'cycle':i+1}
  for f in FIELDS:
   post=f.startswith('commit') or f=='instret';r[('post_' if post else 'pre_')+f]=value_at(s[f],t,not post)
  rows.append(r)
 out=Path('docs/waveforms');out.mkdir(exist_ok=True,parents=True)
 with (out/f'{name}.csv').open('w',newline='') as stream:
  w=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
 left,cell,top,step=235,74,95,33;width=left+cell*len(rows)+15;height=top+step*len(FIELDS)+45
 svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">','<rect width="100%" height="100%" fill="white"/>','<style>text{font-family:Menlo,monospace;font-size:12px;fill:#172d42}</style>',f'<text x="15" y="27" style="font-size:19px">v24 {"dual ALU" if name=="dual-on" else "same lookahead, one ALU"}</text>','<text x="15" y="51">Actual VCD | identical burst program | latency=5, gap=3 | issue pre-edge, commit/counters post-edge</text>']
 for j,r in enumerate(rows):svg.append(f'<text x="{left+j*cell+cell/2}" y="78" text-anchor="middle">C{r["cycle"]}</text>')
 for k,f in enumerate(FIELDS):
  y=top+k*step;key=('post_' if f.startswith('commit') or f=='instret' else 'pre_')+f;svg.append(f'<text x="12" y="{y+18}">{escape(key)}</text>')
  for j,r in enumerate(rows):
   v=r[key];x=left+j*cell;txt=hex(v) if f.endswith(('pc','data')) else str(v);color='#d2f1df' if v==1 and not f.endswith(('pc','data')) else '#f2f5fa'
   svg.extend([f'<rect x="{x+2}" y="{y}" width="{cell-4}" height="26" rx="3" fill="{color}"/>',f'<text x="{x+cell/2}" y="{y+18}" text-anchor="middle">{txt}</text>'])
 svg.extend([f'<text x="15" y="{height-15}">Two retirements share one cycle but retain sequential PCs and independent writes. This is peak width, not sustained frontend bandwidth.</text>','</svg>']);(out/f'{name}.svg').write_text('\n'.join(svg)+'\n')
 return dict(anchor_pc=anchor,issue_cycle=first+1,vcd_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())
if __name__=='__main__':
 image='build/dual_burst.bin';wave='build/dual-burst-onealu.vcd';trace='build/dual-wave-onealu.trace.jsonl'
 subprocess.run(['build/onealu_obj/Vrv64_core',image,'5',wave,'3',trace],check=True,capture_output=True);verify_files(image,trace)
 on=draw('build/dual_burst.vcd','dual-on');off=draw(wave,'dual-onealu',on['anchor_pc'])
 Path('build/dual-wave-manifest.json').write_text(json.dumps(dict(dual=on,lookahead_scalar=off,image_sha256=hashlib.sha256(Path(image).read_bytes()).hexdigest()),indent=2)+'\n');print('DUAL WAVEFORMS PASS: real two-lane issue and ordered two-slot retirement')
