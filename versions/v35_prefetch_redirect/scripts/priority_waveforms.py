"""Actual VCD samples of the matched-demand selector overriding slot-order prefetch."""
import csv,hashlib,json
from html import escape
from pathlib import Path
from waveforms import read_vcd,value_at
FIELDS=['f_valid','f_ready','f_addr','match','matched_demand','choose','legacy_addr','issue_slot','mw_valid','mw_ready','mw_addr','mw_rsp_valid','ifetch_window_pending','commit_valid','commit_pc']

def draw(path,name,enabled):
 s=read_vcd(path);w=read_vcd(path,['TOP','rv64_core','request_window','window'])
 for n in ('match','matched_demand','choose','issue_slot'):s[n]=w[n]
 edges=[t for t,v in s['clk'] if v==1 and not value_at(s['reset'],t,True)]
 def event(t):
  p=lambda n:value_at(s[n],t,True)
  q=lambda n:value_at(w[n],t,True)
  return q('take') and q('found') and not q('issued')&(1<<q('match')) and not q('done')&(1<<q('match')) and q('choose_found') and q('choose')!=q('match') and p('mw_valid') and p('mw_ready')
 first=next(i for i,t in enumerate(edges) if event(t));rows=[]
 for i in range(max(0,first-3),min(len(edges),first+10)):
  t=edges[i];r={'cycle':i+1}
  for f in FIELDS:
   post=f.startswith('commit_')
   r[('post_' if post else 'pre_')+f]=value_at(w[f'address[{value_at(w["choose"],t,True)}]'],t,True) if f=='legacy_addr' else value_at(s[f],t,not post)
  rows.append(r)
 out=Path('docs/waveforms');out.mkdir(exist_ok=True,parents=True)
 with (out/f'{name}.csv').open('w',newline='') as stream:
  writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
 left,cell,top,step=235,72,98,33;width=left+cell*len(rows)+15;height=top+step*len(FIELDS)+50
 svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">','<rect width="100%" height="100%" fill="white"/>','<style>text{font-family:Menlo,monospace;font-size:12px;fill:#172d42}</style>',f'<text x="15" y="27" style="font-size:19px">v21 matched-demand priority {"ON" if enabled else "OFF"}</text>','<text x="15" y="51">Actual C program VCD | identical binary | latency=5, gap=3 | control pre-edge, commit post-edge</text>']
 for j,r in enumerate(rows):svg.append(f'<text x="{left+j*cell+cell/2}" y="81" text-anchor="middle">C{r["cycle"]}</text>')
 for k,f in enumerate(FIELDS):
  y=top+k*step;key=('post_' if f.startswith('commit_') else 'pre_')+f;svg.append(f'<text x="12" y="{y+18}">{escape(key)}</text>')
  for j,r in enumerate(rows):
   v=r[key];x=left+j*cell;txt=hex(v) if f.endswith(('pc','addr','data')) else str(v);color='#d2f1df' if v==1 and not f.endswith(('pc','addr','data')) else '#f2f5fa'
   svg.extend([f'<rect x="{x+2}" y="{y}" width="{cell-4}" height="26" rx="3" fill="{color}"/>',f'<text x="{x+cell/2}" y="{y+18}" text-anchor="middle">{txt}</text>'])
 svg.extend([f'<text x="15" y="{height-16}">legacy_addr = address[choose]. issue_slot identifies the accepted request owner, not necessarily choose.</text>','</svg>']);(out/f'{name}.svg').write_text('\n'.join(svg)+'\n')
 t=edges[first];return dict(vcd=path,vcd_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),first_override_opportunity_cycle=first+1,demand_addr=value_at(s['f_addr'],t,True),selected_addr=value_at(s['mw_addr'],t,True))

if __name__=='__main__':
 info={mode:draw(f'build/priority-c-{mode}.vcd','priority-on' if enabled else 'priority-off',enabled) for mode,enabled in [('full',True),('nopriority',False)]}
 info['image_sha256']=hashlib.sha256(Path('build/priority_c.bin').read_bytes()).hexdigest()
 Path('build/priority-wave-manifest.json').write_text(json.dumps(info,indent=2)+'\n')
 print('DEMAND PRIORITY WAVEFORMS PASS: actual C on/off slot selection and accepted address')
