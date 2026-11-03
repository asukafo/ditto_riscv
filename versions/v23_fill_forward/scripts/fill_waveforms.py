"""Render first eligible background hit in identical on/off core executions."""
import csv,hashlib,json
from html import escape
from pathlib import Path
from waveforms import read_vcd,value_at
FIELDS=['cache_state','fill_addr','beat','cache_addr','fill_match','background_accept','cache_valid','cache_ready','cache_rsp_valid','cache_rsp_ready','cache_rsp_data','physical_pending','window_pending','commit_valid','commit_pc']
ALIASES={'cache_state':'state','fill_addr':'address','beat':'beat','cache_addr':'u_addr','fill_match':'fill_match','background_accept':'background_accept','cache_valid':'u_valid','cache_ready':'u_ready','cache_rsp_valid':'u_rsp_valid','cache_rsp_ready':'u_rsp_ready','cache_rsp_data':'u_rsp_data'}

def draw(path,name,enabled):
 s=read_vcd(path);c=read_vcd(path,['TOP','rv64_core','memory_system','split','icache'])
 edges=[t for t,v in s['clk'] if v==1 and not value_at(s['reset'],t,True)];counts=[];physical=0
 for t in edges:
  counts.append(physical)
  physical+=bool(value_at(s['req_valid'],t,True) and value_at(s['req_ready'],t,True))
  physical-=bool(value_at(s['rsp_valid'],t,True) and value_at(s['rsp_ready'],t,True));assert 0<=physical<=1
 def event(t):
  q=lambda n:value_at(c[n],t,True)
  return q('state') in (2,3) and q('early') and q('beat') and not q('poisoned') and q('cacheable') and q('first_fits') and q('u_addr')>>3==q('address')>>3 and not q('invalidate') and q('u_valid') and (not q('response_available') or q('u_rsp_ready'))
 first=next(i for i,t in enumerate(edges) if event(t));rows=[]
 for i in range(max(0,first-3),min(len(edges),first+11)):
  t=edges[i];r={'cycle':i+1}
  for f in FIELDS:
   post=f.startswith('commit_')
   r[('post_' if post else 'pre_')+f]=counts[i] if f=='physical_pending' else value_at(c[ALIASES[f]],t,True) if f in ALIASES else value_at(s['ifetch_window_pending' if f=='window_pending' else f],t,not post)
  rows.append(r)
 out=Path('docs/waveforms');out.mkdir(exist_ok=True,parents=True)
 with (out/f'{name}.csv').open('w',newline='') as stream:
  writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
 left,cell,top,step=238,72,98,33;width=left+cell*len(rows)+15;height=top+step*len(FIELDS)+50
 svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">','<rect width="100%" height="100%" fill="white"/>','<style>text{font-family:Menlo,monospace;font-size:12px;fill:#172d42}</style>',f'<text x="15" y="27" style="font-size:19px">v23 verified refill-half forwarding {"ON" if enabled else "OFF"}</text>','<text x="15" y="51">Actual C VCD | identical binary | latency=5, gap=3 | controls pre-edge; commit post-edge</text>']
 for j,r in enumerate(rows):svg.append(f'<text x="{left+j*cell+cell/2}" y="81" text-anchor="middle">C{r["cycle"]}</text>')
 for k,f in enumerate(FIELDS):
  y=top+k*step;key=('post_' if f.startswith('commit_') else 'pre_')+f;svg.append(f'<text x="12" y="{y+18}">{escape(key)}</text>')
  for j,r in enumerate(rows):
   v=r[key];x=left+j*cell;txt=hex(v) if f.endswith(('pc','addr','data')) else str(v);color='#d2f1df' if v==1 and not f.endswith(('pc','addr','data')) else '#f2f5fa'
   font=11 if f=='cache_rsp_data' else 12
   svg.extend([f'<rect x="{x+2}" y="{y}" width="{cell-4}" height="26" rx="3" fill="{color}"/>',f'<text x="{x+cell/2}" y="{y+18}" text-anchor="middle" style="font-size:{font}px">{txt}</text>'])
 svg.extend([f'<text x="15" y="{height-16}">Cache states: 2 refill request, 3 refill response, 4 held response. Physical pending is accepted minus returned external transactions.</text>','</svg>']);(out/f'{name}.svg').write_text('\n'.join(svg)+'\n')
 t=edges[first];return dict(vcd=path,vcd_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),first_opportunity_cycle=first+1,fill_addr=value_at(c['address'],t,True),hit_addr=value_at(c['u_addr'],t,True))

if __name__=='__main__':
 info={mode:draw(f'build/fill-c-{mode}.vcd','fill-on' if enabled else 'fill-off',enabled) for mode,enabled in [('full',True),('nofill',False)]}
 assert info['full']['first_opportunity_cycle']==info['nofill']['first_opportunity_cycle']
 info['image_sha256']=hashlib.sha256(Path('build/under_c.bin').read_bytes()).hexdigest()
 Path('build/fill-wave-manifest.json').write_text(json.dumps(info,indent=2)+'\n')
 print('HIT UNDER REFILL WAVEFORMS PASS: actual first background-hit on/off samples')
