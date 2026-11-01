"""Export cold-refill and warm-hit edge samples from the real cache VCD."""
import csv
from html import escape
from pathlib import Path
from waveforms import read_vcd,value_at


def draw(signals,edges,first,last,name,title):
    fields=['fe_valid','fe_pc','fe_predicted_next','fe_predicted_dynamic',
            'state','pc','ex_predicted_next','bht_prediction_event','control_miss_event',
            'redirect','bht_train_event','wb_pc','wb_branch_taken','commit_valid','commit_pc']
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
    svg.append(f'<text x="15" y="{height-20}">Training uses W-stage PC and actual direction. A learned prediction is saved with each F packet; X recovers every miss.</text>')
    svg.append('</svg>');(output/f'{name}.svg').write_text('\n'.join(svg)+'\n')


def main():
    signals=read_vcd('build/bht.vcd')
    edges=[t for t,v in signals['clk'] if v==1 and value_at(signals['reset'],t,True)==0]
    cold=next(i for i,t in enumerate(edges) if value_at(signals['conditional_resolve_event'],t,True) and value_at(signals['control_miss_event'],t,True))
    warm=next(i for i,t in enumerate(edges) if value_at(signals['bht_prediction_event'],t,True))
    draw(signals,edges,max(0,cold-3),cold+11,'bht-cold','v12 cold forward branch: static miss, then committed taken training')
    draw(signals,edges,max(0,warm-5),warm+9,'bht-learned','v12 learned forward branch: dynamic target, no recovery redirect')
    print(f'BHT WAVEFORMS: cold miss C{cold+1}, learned resolve C{warm+1}')


if __name__=='__main__':main()
