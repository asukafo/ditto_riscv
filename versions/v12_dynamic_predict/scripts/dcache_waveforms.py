"""Export cold-refill and warm-hit edge samples from the real cache VCD."""
import csv
from html import escape
from pathlib import Path
from waveforms import read_vcd,value_at


def draw(signals,edges,first,last,name,title):
    fields=['dcache_miss_event','dcache_hit_event','dcache_refill_event','dcache_miss_wait',
            'req_valid','req_ready','req_addr','req_size','rsp_valid','rsp_ready',
            'd_rsp_valid','data_rsp_ready','fe_valid','issue_fire','commit_valid','commit_pc']
    rows=[]
    for i in range(first,min(last,len(edges))):
        t=edges[i];row={'cycle':i+1}
        for field in fields:
            post=field in ('commit_valid','commit_pc')
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
        y=top+k*step;key=('post_' if field in ('commit_valid','commit_pc') else 'pre_')+field
        svg.append(f'<text x="12" y="{y+18}">{escape(key)}</text>')
        for j,row in enumerate(rows):
            value=row[key];x=left+j*cell
            text=hex(value) if field in ('req_addr','commit_pc') else str(value)
            color='#d2f1df' if value==1 and field not in ('req_addr','commit_pc','req_size') else '#f2f5fa'
            svg.append(f'<rect x="{x+2}" y="{y}" width="{cell-4}" height="27" rx="3" fill="{color}"/>')
            svg.append(f'<text x="{x+cell/2}" y="{y+18}" text-anchor="middle">{text}</text>')
    svg.append(f'<text x="15" y="{height-20}">req_size=3 means an 8-byte refill beat. Bus fields matter only when valid. Time is simulation cycles.</text>')
    svg.append('</svg>');(output/f'{name}.svg').write_text('\n'.join(svg)+'\n')


def main():
    signals=read_vcd('build/dcache.vcd')
    edges=[t for t,v in signals['clk'] if v==1 and value_at(signals['reset'],t,True)==0]
    cold=next(i for i,t in enumerate(edges) if value_at(signals['dcache_miss_event'],t,True))
    warm=next(i for i,t in enumerate(edges) if i>cold and value_at(signals['dcache_hit_event'],t,True))
    draw(signals,edges,max(0,cold-1),cold+28,'dcache-cold','v12 data cache: early load response overlaps background refill')
    draw(signals,edges,max(0,warm-2),warm+14,'dcache-warm','v12 data cache: repeated load hits without external data reads')
    print(f'DATA CACHE WAVEFORMS: cold miss C{cold+1}, warm window C{warm+1}')


if __name__=='__main__':main()
