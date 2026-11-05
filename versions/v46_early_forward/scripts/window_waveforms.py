"""Export cold-refill and warm-hit edge samples from the real cache VCD."""
import csv
from html import escape
from pathlib import Path
from waveforms import read_vcd,value_at


def draw(signals,edges,first,last,name,title):
    fields=['ifetch_window_pending','mw_valid','mw_ready','mw_addr','mw_rsp_valid','mw_rsp_ready',
            'window_owner','window_poison','window_retarget','ifetch_window_drop_event','fetch_redirect',
            'fe_valid','fe_pc','issue_fire','commit_valid','commit_pc']
    rows=[]
    for i in range(first,min(last,len(edges))):
        t=edges[i];row={'cycle':i+1}
        for field in fields:
            post=field in ('commit_valid','commit_pc','commit_next_pc')
            row[('post_' if post else 'pre_')+field]=value_at(signals[field],t,not post)
        rows.append(row)
    output=Path('docs/waveforms');output.mkdir(parents=True,exist_ok=True)
    with (output/f'{name}.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n')
        writer.writeheader();writer.writerows(rows)
    left,cell,top,step=245,67,98,34
    width=left+cell*len(rows)+15;height=top+step*len(fields)+58
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
         '<rect width="100%" height="100%" fill="white"/>',
         '<style>text{font-family:Menlo,monospace;font-size:12px;fill:#172d42}</style>',
         f'<text x="15" y="27" style="font-size:19px">{escape(title)}</text>',
         '<text x="15" y="51">Actual VCD | latency=5, gap=3 | control before edge; commit after edge</text>']
    for j,row in enumerate(rows):
        x=left+j*cell
        svg.append(f'<text x="{x+cell/2}" y="81" text-anchor="middle">C{row["cycle"]}</text>')
    for k,field in enumerate(fields):
        y=top+k*step;key=('post_' if field in ('commit_valid','commit_pc','commit_next_pc') else 'pre_')+field
        svg.append(f'<text x="12" y="{y+18}">{escape(key)}</text>')
        for j,row in enumerate(rows):
            value=row[key];x=left+j*cell
            text=hex(value) if field.endswith(('pc','next','addr')) else str(value)
            color='#d2f1df' if value==1 and not field.endswith(('pc','next','addr')) else '#f2f5fa'
            svg.append(f'<rect x="{x+2}" y="{y}" width="{cell-4}" height="27" rx="3" fill="{color}"/>')
            svg.append(f'<text x="{x+cell/2}" y="{y+18}" text-anchor="middle">{text}</text>')
    svg.append(f'<text x="15" y="{height-20}">Pending = accepted I requests minus returned I responses. External physical bus still permits only one transaction.</text>')
    svg.append('</svg>');(output/f'{name}.svg').write_text('\n'.join(svg)+'\n')


def load(path):
 s=read_vcd(path);w=read_vcd(path,['TOP','rv64_core','request_window','window'])
 for name in ('owner','poison','retarget'):s['window_'+name]=w[name]
 return s,[t for t,v in s['clk'] if v==1 and not value_at(s['reset'],t,True)]
s,e=load('build/window_stream.vcd')
i=next(i for i,t in enumerate(e) if value_at(s['ifetch_window_pending'],t)==2)
draw(s,e,max(0,i-4),i+11,'window-double','v17 two accepted instruction requests before the first response returns')
s,e=load('build/window_fence.vcd')
i=next(i for i,t in enumerate(e) if value_at(s['ifetch_window_drop_event'],t,True))
draw(s,e,max(0,i-5),i+9,'window-poison','v17 stale response returns to its original slot and is discarded')
print('WINDOW WAVEFORMS: actual dual-outstanding and poisoned completion samples')
