"""Measure dual-lane on/off without treating peak retirement width as sustained IPC."""
import csv,json,subprocess
from collections import Counter
from pathlib import Path
from reference import verify_files
rows=[]
for name in ['burst','zero','raw','waw','war','forward','csr','compressed','exception','flush','load']:
 for l,g in [(1,0),(5,0),(5,3)]:
  pair=[]
  for mode in ['full','onealu','nodual']:
   trace=f'build/dual-ablation-{name}-{mode}-l{l}-g{g}.trace.jsonl';s=json.loads(subprocess.check_output([f'build/{mode}_obj/Vrv64_core',f'build/dual_{name}.bin',str(l),'-',str(g),trace],text=True));assert verify_files(f'build/dual_{name}.bin',trace)==s['instret']
   records=[json.loads(x) for x in Path(trace).read_text().splitlines()];counts=Counter(r['cycle'] for r in records if r['kind']=='commit');peak=max(counts.values());assert peak<=2
   if mode!='full':assert peak==1 and s['dual_issue_pairs']==s['dual_issue_enabled']==0
   assert s['issue_lookahead_enabled']==(mode!='nodual')
   pair.append((s,peak))
  on,look,off=pair;assert on[0]['result']==off[0]['result']==look[0]['result'] and on[0]['instret']==off[0]['instret']==look[0]['instret']
  rows.append(dict(program=name,latency=l,gap=g,on_cycles=on[0]['cycles'],lookahead_only_cycles=look[0]['cycles'],off_cycles=off[0]['cycles'],paired_issues=on[0]['dual_issue_pairs'],peak_commits_per_cycle=on[1]))
assert any(x['peak_commits_per_cycle']==2 for x in rows)
with Path('build/dual-ablation.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
print('DUAL ABLATION PASS: 99 checked three-way runs; explicit 1/2 retirement-width counts')
