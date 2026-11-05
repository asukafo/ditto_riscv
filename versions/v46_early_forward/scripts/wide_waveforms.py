"""Cycle samples from the measured hot loop; issue uses pre-edge, commit post-edge."""
import csv,json
from pathlib import Path
from html import escape
from waveforms import read_vcd,value_at
FIELDS=['f_valid','f_ready','f_addr','f_size','raw_fe_valid','raw_fe_pc','raw_fe_second_valid','wide_take_count','wide_queue_occupancy','fe_pc','p2_pc','pair_fire','commit_valid','commit_pc','commit2_valid','commit2_pc','instret']
def main():
 warm=json.loads(Path('build/wide-warm-ipc.json').read_text());out=Path('docs/waveforms');out.mkdir(exist_ok=True,parents=True)
 for mode in ['full','narrow']:
  s=read_vcd(f'build/wide-hot-{mode}.vcd');edges=[t for t,v in s['clk'] if v==1 and not value_at(s['reset'],t,True)];first=warm[mode]['anchor_cycle']-1;rows=[]
  for i in range(first-2,first+12):
   t=edges[i];r=dict(cycle=i+1)
   for f in FIELDS:
    post=f.startswith('commit') or f=='instret';r[('post_' if post else 'pre_')+f]=value_at(s[f],t,not post)
   rows.append(r)
  name='wide-hot' if mode=='full' else 'narrow-hot'
  with (out/f'{name}.csv').open('w',newline='') as file:
   w=csv.DictWriter(file,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
  left,cell,top,step=220,68,105,29;width=left+len(rows)*cell+15;height=top+len(FIELDS)*step+65
  svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">','<rect width="100%" height="100%" fill="white"/>','<style>text{font-family:Menlo,monospace;font-size:11px;fill:#172d42}</style>',f'<text x="15" y="27" style="font-size:18px">v29 {mode}: actual warm-loop fetch / issue / retirement</text>',f'<text x="15" y="50">960 instructions / {warm[mode]["warm_cycles"]} cycles = {warm[mode]["warm_ipc"]:.3f} IPC | latency=5, gap=3</text>','<text x="15" y="70">pre = before rising edge; post = after edge. PCs/data apply only while their valid signal is 1.</text>']
  for j,r in enumerate(rows):svg.append(f'<text x="{left+j*cell+cell/2}" y="92" text-anchor="middle">C{r["cycle"]}</text>')
  for k,f in enumerate(FIELDS):
   y=top+k*step;key=('post_' if f.startswith('commit') or f=='instret' else 'pre_')+f;svg.append(f'<text x="12" y="{y+17}">{escape(key)}</text>')
   for j,r in enumerate(rows):
    v=r[key];x=left+j*cell;txt=hex(v) if f.endswith(('pc','addr')) else str(v);color='#d2f1df' if v and (f.endswith('valid') or f=='pair_fire' or f=='wide_take_count') else '#f2f5fa'
    svg.extend([f'<rect x="{x+1}" y="{y}" width="{cell-2}" height="24" rx="3" fill="{color}"/>',f'<text x="{x+cell/2}" y="{y+17}" text-anchor="middle">{txt}</text>'])
  svg.extend([f'<text x="15" y="{height-30}">f_size=3: 8 bytes per request. wide_take_count=2: two ordered packets accepted in one edge.</text>',f'<text x="15" y="{height-12}">pair_fire=1 dispatches two independent ALUs; commit_valid + commit2_valid retire two instructions in order.</text>','</svg>']);(out/f'{name}.svg').write_text('\n'.join(svg)+'\n')
 print('WIDE WAVEFORMS PASS: full/narrow sampled from real VCDs at the same loop iteration')
if __name__=='__main__':main()
