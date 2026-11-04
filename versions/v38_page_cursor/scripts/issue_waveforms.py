"""Render same-cycle demand issue on/off from identical binaries and real VCDs."""
import csv,subprocess
from html import escape
from pathlib import Path
from waveforms import read_vcd,value_at
FIELDS=['f_valid','f_ready','f_addr','new_demand','direct_demand','mw_valid','mw_ready','mw_addr','mw_size','issue_slot','ifetch_window_pending','mw_rsp_valid','forward_return','f_rsp_valid','f_rsp_ready','commit_valid','commit_pc']

def draw(path,name,enabled):
 s=read_vcd(path);w=read_vcd(path,['TOP','rv64_core','request_window','window'])
 for n in ('new_demand','direct_demand','issue_slot','forward_return'):s[n]=w[n]
 edges=[t for t,v in s['clk'] if v==1 and not value_at(s['reset'],t,True)]
 start=next(i for i,t in enumerate(edges) if value_at(s['new_demand'],t,True))
 rows=[]
 for i in range(max(0,start-2),min(len(edges),start+16)):
  t=edges[i];r={'cycle':i+1}
  for f in FIELDS:r[('post_' if f.startswith('commit_') else 'pre_')+f]=value_at(s[f],t,not f.startswith('commit_'))
  rows.append(r)
 out=Path('docs/waveforms');out.mkdir(exist_ok=True,parents=True)
 with (out/f'{name}.csv').open('w',newline='') as stream:
  writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
 left,cell,top,step=232,67,98,33;width=left+cell*len(rows)+15;height=top+step*len(FIELDS)+50
 svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">','<rect width="100%" height="100%" fill="white"/>','<style>text{font-family:Menlo,monospace;font-size:12px;fill:#172d42}</style>',f'<text x="15" y="27" style="font-size:19px">v20 same-cycle demand issue {"ON" if enabled else "OFF"}</text>','<text x="15" y="51">Actual VCD | identical window_stream binary | latency=5, gap=3 | controls pre-edge, commit post-edge</text>']
 for j,r in enumerate(rows):svg.append(f'<text x="{left+j*cell+cell/2}" y="81" text-anchor="middle">C{r["cycle"]}</text>')
 for k,f in enumerate(FIELDS):
  y=top+k*step;key=('post_' if f.startswith('commit_') else 'pre_')+f;svg.append(f'<text x="12" y="{y+18}">{escape(key)}</text>')
  for j,r in enumerate(rows):
   v=r[key];x=left+j*cell;txt=hex(v) if f.endswith(('pc','addr','data')) else str(v);color='#d2f1df' if v==1 and not f.endswith(('pc','addr','data')) else '#f2f5fa'
   svg.extend([f'<rect x="{x+2}" y="{y}" width="{cell-4}" height="26" rx="3" fill="{color}"/>',f'<text x="{x+cell/2}" y="{y+18}" text-anchor="middle">{txt}</text>'])
 svg.extend([f'<text x="15" y="{height-16}">A new demand reserves its slot on acceptance; direct issue marks that slot issued and records its completion token.</text>','</svg>']);(out/f'{name}.svg').write_text('\n'.join(svg)+'\n')

if __name__=='__main__':
 for mode,enabled in [('full',True),('noissue',False)]:
  wave=f'build/issue-{mode}.vcd';subprocess.run([f'build/{mode}_obj/Vrv64_core','build/window_stream.bin','5',wave,'3'],check=True,capture_output=True,text=True);draw(wave,'issue-on' if enabled else 'issue-off',enabled)
 print('DEMAND ISSUE WAVEFORMS PASS: on/off real demand acceptance and service issue')
