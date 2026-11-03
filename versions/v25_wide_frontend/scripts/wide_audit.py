"""Independent ordered model for every 333-bit packet at the two-port boundary."""
from collections import deque
from waveforms import read_vcd,value_at

def audit(path):
 s=read_vcd(path);q=deque();peak=flushes=busy=exchanges=inflight=partial=push2=pop2=held_cycles=0;held=None
 fields=('pc','predicted_next','cause','value','insn','raw','bytes','illegal','fault','predicted_return','predicted_dynamic','predicted_btb','predicted_index');widths=(64,64,64,64,32,32,3,1,1,1,1,1,5)
 for t,v in s['clk']:
  if not v or value_at(s['reset'],t,True):continue
  p=lambda n:value_at(s[n],t,True)
  assert p('wide_fetch_enabled') and p('wide_queue_occupancy')==len(q)
  flush=p('fetch_redirect');n=(1+bool(p('raw_fe_second_valid'))) if p('raw_fe_valid') else 0
  raw=0
  for f,w in zip(fields,widths):raw=(raw<<w)|p('raw_fe_'+f)
  packet=(raw,p('raw_fe_second_packet'))
  if held is not None and not flush:assert n==held[0] and packet[:n]==held[1];held_cycles+=1
  available=list(q)+list(packet[:n])
  assert bool(p('fe_valid'))==bool(available and not flush)
  assert bool(p('second_valid'))==bool(len(available)>=2 and not flush)
  if p('fe_valid'):assert p('fe_packet')==available[0]
  if p('second_valid'):assert p('second_packet')==available[1]
  pop=(2 if p('pair_fire') else 1) if p('issue_fire') else 0
  assert pop<=len(available)
  take=0 if flush else min(n,6-len(q)+pop)
  assert p('wide_take_count')==take and bool(p('raw_fe_ready'))==bool(take)
  if n==2:
   a,b=packet;pc=a>>269;size=(a>>10)&7;pc2=b>>269
   assert pc2==pc+size and ((a>>205)&((1<<64)-1))==pc2
  peak=max(peak,len(q));exchanges+=len(q)==6 and pop==take==2;partial+=n==2 and take==1;push2+=take==2;pop2+=pop==2;busy+=bool(take and p('state')!=0 and not p('ex_finish'))
  held=(n,packet[:n]) if n and not take and not flush else None
  if flush:flushes+=bool(q);q.clear()
  else:
   q.extend(packet[:take])
   for _ in range(pop):q.popleft()
  assert value_at(s['wide_queue_occupancy'],t)==len(q)
  if p('f_rsp_valid') and p('f_rsp_ready'):inflight-=1
  if p('f_valid') and p('f_ready'):inflight+=1
  assert 0<=inflight<=1
 return dict(peak=peak,nonempty_flushes=flushes,fill_while_x_busy=busy,full_pop_push=exchanges,max_outstanding_fetches=1,push2=push2,pop2=pop2,partial_accepts=partial,held_cycles=held_cycles)
