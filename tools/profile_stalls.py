"""Measure pipeline stalls from pre-edge VCD values without changing frozen RTL."""
from bisect import bisect_left
import json
from pathlib import Path
import sys

SIGNALS = {
    'clk':'clk', 'reset':'reset', 'halted':'halted', 'state':'state', 'fe_valid':'fe_valid',
    'serial':'serialize_pending', 'irq':'irq_stop', 'arb_state':'arbiter.state',
    'owner':'arbiter.owner_data', 'd_valid':'arbiter.d_valid', 'f_valid':'arbiter.f_valid',
    'rsp_ready':'frontend.rsp_ready', 'rsp_valid':'frontend.rsp_valid',
    'direct_data_block':'data_blocked_by_fetch', 'direct_fetch_block':'fetch_blocked_by_data',
    'killed':'frontend.killed', 'redirect':'frontend.redirect',
}


def profile(path):
    wanted={'TOP.rv64_core.'+name:key for key,name in SIGNALS.items()}
    scopes=[];codes={};traces={key:[] for key in SIGNALS};stamp=0
    with Path(path).open() as stream:
        for line in stream:
            words=line.split()
            if not words:continue
            if words[0]=='$scope':scopes.append(words[2])
            elif words[0]=='$upscope':scopes.pop()
            elif words[0]=='$var':
                full='.'.join(scopes+[words[4]])
                if full in wanted:codes.setdefault(words[3],[]).append(wanted[full])
            elif line.startswith('#'):stamp=int(line[1:])
            elif line[0] in '01bxz':
                value,code=(words[0][1:],words[1]) if line[0]=='b' else (line[0],line[1:].strip())
                if code not in codes:continue
                if any(c in value for c in 'xz'):raise ValueError(f'Unknown VCD value in {codes[code]}')
                for key in codes[code]:
                    value_int=int(value,2)
                    if not traces[key] or traces[key][-1][1]!=value_int:traces[key].append((stamp,value_int))
    direct=bool(traces['direct_data_block'] and traces['direct_fetch_block'])
    optional={'arb_state','owner','d_valid','f_valid'} if direct else {'direct_data_block','direct_fetch_block'}
    missing=[key for key,trace in traces.items() if not trace and key not in optional]
    if missing:raise ValueError(f'Missing VCD signals: {missing}')
    times={key:[t for t,v in trace] for key,trace in traces.items()}
    def before(key,t):
        index=bisect_left(times[key],t)-1
        return traces[key][index][1] if index>=0 else 0
    result=dict(sampled_cycles=0,frontend_starved_cycles=0,data_blocked_by_fetch_cycles=0,
                fetch_blocked_by_data_cycles=0,discarded_fetch_responses=0)
    for t,value in traces['clk']:
        if value!=1 or before('reset',t):continue
        s={key:before(key,t) for key in SIGNALS if traces[key]}
        result['sampled_cycles']+=1
        result['frontend_starved_cycles']+=int(not s['halted'] and s['state']==0 and not s['fe_valid'] and not s['serial'] and not s['irq'])
        if direct:
            result['data_blocked_by_fetch_cycles']+=s['direct_data_block']
            result['fetch_blocked_by_data_cycles']+=s['direct_fetch_block']
        else:
            result['data_blocked_by_fetch_cycles']+=int(s['d_valid'] and s['arb_state']!=0 and not s['owner'])
            result['fetch_blocked_by_data_cycles']+=int(s['f_valid'] and ((s['arb_state']!=0 and s['owner']) or (s['arb_state']==0 and s['d_valid'])))
        result['discarded_fetch_responses']+=int(s['rsp_ready'] and s['rsp_valid'] and (s['killed'] or s['redirect']))
    return result


if __name__=='__main__':
    print(json.dumps(profile(sys.argv[1]),indent=2))
