"""Sample the actual VCD around the first forwarding event; export SVG and CSV."""
import csv
from html import escape
from pathlib import Path
from waveforms import read_vcd,value_at


def main():
    signals=read_vcd('build/pipeline.vcd')
    edges=[t for t,v in signals['clk'] if v==1 and value_at(signals['reset'],t)==0]
    focus=next(i for i,t in enumerate(edges) if value_at(signals['bypass_count'],t)>
               value_at(signals['bypass_count'],t,True))
    first=max(0,focus-5);last=min(len(edges),focus+12)
    fields=['fe_valid','state','pc','wb_valid','wb_pc','issue_fire','retire',
            'commit_valid','commit_pc','bypass_count']
    rows=[]
    for i in range(first,last):
        t=edges[i]
        row={'cycle':i+1}
        for name in fields:
            post=name in ('commit_valid','commit_pc','bypass_count')
            row[('post_' if post else 'pre_')+name]=value_at(signals[name],t,not post)
        rows.append(row)
    output=Path('docs/waveforms');output.mkdir(parents=True,exist_ok=True)
    with (output/'pipeline.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    left,cell,top,step=195,75,100,39
    width=left+cell*len(rows)+15;height=top+step*len(fields)+65
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
         '<rect width="100%" height="100%" fill="white"/>',
         '<style>text{font-family:Menlo,monospace;font-size:13px;fill:#172d42}</style>',
         '<text x="15" y="27" style="font-size:20px">v2 single-issue pipeline: actual VCD edge samples</text>',
         '<text x="15" y="51">Control: before edge | commit/counter: after edge | X=execution, W=commit</text>']
    for j,row in enumerate(rows):
        x=left+j*cell
        svg.append(f'<text x="{x+cell/2}" y="83" text-anchor="middle">C{row["cycle"]}</text>')
        svg.append(f'<line x1="{x}" y1="90" x2="{x}" y2="{height-50}" stroke="#dce3ec"/>')
    states={0:'EMPTY',1:'EXEC',2:'DREQ',3:'DRSP',4:'MDWAIT'}
    for k,name in enumerate(fields):
        y=top+k*step
        post=name in ('commit_valid','commit_pc','bypass_count')
        key=('post_' if post else 'pre_')+name
        svg.append(f'<text x="12" y="{y+19}">{escape(key)}</text>')
        for j,row in enumerate(rows):
            x=left+j*cell;v=row[key]
            text=states[v] if name=='state' else hex(v) if name.endswith('pc') or name=='pc' else str(v)
            active=(v==1 and name.endswith(('valid','fire','retire')))
            color='#d2f1df' if active else '#f2f5fa'
            svg.append(f'<rect x="{x+2}" y="{y}" width="{cell-4}" height="28" rx="3" fill="{color}"/>')
            svg.append(f'<text x="{x+cell/2}" y="{y+19}" text-anchor="middle">{text}</text>')
    svg.append(f'<text x="15" y="{height-22}">PC values matter only when the corresponding stage is valid. Time is cycles, not physical delay.</text>')
    svg.append('</svg>')
    (output/'pipeline.svg').write_text('\n'.join(svg)+'\n')
    print(f'Generated {output}/pipeline.svg and pipeline.csv; first bypass at C{focus+1}')


if __name__=='__main__':main()
