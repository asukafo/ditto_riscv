"""Export cold-refill and warm-hit edge samples from the real cache VCD."""
import csv
from html import escape
from pathlib import Path
from waveforms import read_vcd,value_at


def draw(signals,edges,first,last,name,title):
    fields=['state','pc','raw_fe_valid','raw_fe_ready','raw_fe_pc','fetch_queue_occupancy',
            'fetch_queue_push_event','fetch_queue_pop_event','fetch_queue_full_stall',
            'fe_valid','fe_ready','fe_pc','issue_fire','redirect','commit_valid','commit_pc']
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
    svg.append(f'<text x="15" y="{height-20}">Queue stores complete instruction packets, not architectural state. Redirect clears queued packets; the fetcher drains its outstanding read.</text>')
    svg.append('</svg>');(output/f'{name}.svg').write_text('\n'.join(svg)+'\n')


def main():
    signals=read_vcd('build/queue-divide.vcd')
    edges=[t for t,v in signals['clk'] if v==1 and value_at(signals['reset'],t,True)==0]
    fill=next(i for i,t in enumerate(edges) if value_at(signals['fetch_queue_push_event'],t,True) and value_at(signals['state'],t,True)==4)
    drain=next(i for i,t in enumerate(edges) if value_at(signals['fetch_queue_pop_event'],t,True) and value_at(signals['state'],t,True)==4)
    draw(signals,edges,max(0,fill-2),fill+20,'fetch-queue-fill','v15 division stalls X while the frontend fills complete instruction packets')
    draw(signals,edges,max(0,drain-3),drain+13,'fetch-queue-drain','v15 division completes: queued instructions issue without an empty-queue delay')
    signals=read_vcd('build/queue-flush.vcd')
    edges=[t for t,v in signals['clk'] if v==1 and value_at(signals['reset'],t,True)==0]
    flush=next(i for i,t in enumerate(edges) if value_at(signals['redirect'],t,True) and value_at(signals['fetch_queue_occupancy'],t,True)>0)
    draw(signals,edges,max(0,flush-3),flush+11,'fetch-queue-flush','v15 branch correction discards queued stores and illegal instructions')
    print(f'FETCH QUEUE WAVEFORMS: fill C{fill+1}, drain C{drain+1}, redirect C{flush+1}')


if __name__=='__main__':main()
