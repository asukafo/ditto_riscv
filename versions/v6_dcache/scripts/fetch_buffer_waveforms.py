"""Export actual halfword reuse and F/X/W overlap from the compressed test VCD."""
import csv
from html import escape
from pathlib import Path
from waveforms import read_vcd,value_at


def main():
    signals=read_vcd('build/fetch-buffer.vcd')
    edges=[t for t,v in signals['clk'] if v==1 and value_at(signals['reset'],t,True)==0]
    focus=next(i for i,t in enumerate(edges) if value_at(signals['fetch_buffer_reuse_event'],t,True))
    fields=['fe_valid','fe_pc','fetch_buffer_reuse_event','icache_hit_event','icache_miss_event',
            'req_valid','req_addr','issue_fire','state','pc','wb_valid','wb_pc','commit_valid','commit_pc']
    rows=[]
    for i in range(max(0,focus-2),min(len(edges),focus+16)):
        row={'cycle':i+1}
        for field in fields:
            post=field in ('commit_valid','commit_pc')
            row[('post_' if post else 'pre_')+field]=value_at(signals[field],edges[i],not post)
        rows.append(row)
    output=Path('docs/waveforms');output.mkdir(parents=True,exist_ok=True)
    with (output/'fetch-buffer.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n')
        writer.writeheader();writer.writerows(rows)
    left,cell,top,step=255,69,98,34
    width=left+cell*len(rows)+15;height=top+step*len(fields)+58
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
         '<rect width="100%" height="100%" fill="white"/>',
         '<style>text{font-family:Menlo,monospace;font-size:12px;fill:#172d42}</style>',
         '<text x="15" y="27" style="font-size:19px">v6 halfword buffer: reuse without another instruction-cache lookup</text>',
         '<text x="15" y="51">Actual VCD | latency=1, gap=0 | control before edge; commit after edge</text>']
    states={0:'EMPTY',1:'EXEC',2:'DREQ',3:'DRSP',4:'MDWAIT'}
    for j,row in enumerate(rows):
        svg.append(f'<text x="{left+j*cell+cell/2}" y="81" text-anchor="middle">C{row["cycle"]}</text>')
    for k,field in enumerate(fields):
        y=top+k*step;key=('post_' if field in ('commit_valid','commit_pc') else 'pre_')+field
        svg.append(f'<text x="12" y="{y+18}">{escape(key)}</text>')
        for j,row in enumerate(rows):
            value=row[key];x=left+j*cell
            label=states[value] if field=='state' else hex(value) if field.endswith(('pc','addr')) else str(value)
            active=value==1 and field not in ('state','pc','fe_pc','wb_pc','commit_pc','req_addr')
            color='#d2f1df' if active else '#f2f5fa'
            svg.append(f'<rect x="{x+2}" y="{y}" width="{cell-4}" height="27" rx="3" fill="{color}"/>')
            svg.append(f'<text x="{x+cell/2}" y="{y+18}" text-anchor="middle">{label}</text>')
    svg.append(f'<text x="15" y="{height-20}">reuse_event consumes a saved halfword. Stage PCs matter only while valid. No physical frequency is implied.</text>')
    svg.append('</svg>');(output/'fetch-buffer.svg').write_text('\n'.join(svg)+'\n')
    print(f'FETCH BUFFER WAVEFORM: first reuse C{focus+1}')


if __name__=='__main__':main()
