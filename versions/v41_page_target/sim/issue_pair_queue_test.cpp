#include "Vrv64_issue_pair_queue.h"
#include "verilated.h"
#include <deque>
#include <cassert>
#include <iostream>
#ifndef EXPECT_DUAL
#define EXPECT_DUAL 1
#endif
int main(){Vrv64_issue_pair_queue d;std::deque<uint32_t> q;uint64_t rng=0x4af823;unsigned pairs=0,exchanges=0;
 d.clk=0;d.reset=1;d.flush=0;d.u_valid=0;d.u_packet=0;d.pop_count=0;d.eval();d.clk=1;d.eval();d.reset=0;
 for(unsigned c=0;c<50000;++c){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;bool flush=c%107==33;bool uv=(rng&7)!=0;uint32_t packet=rng>>20;
  unsigned available=EXPECT_DUAL?q.size()+unsigned(uv):unsigned(uv);unsigned pop=(rng>>5)%3;if(pop>available)pop=available;if(!EXPECT_DUAL&&pop>1)pop=1;
  d.clk=0;d.flush=flush;d.u_valid=uv;d.u_packet=packet;d.pop_count=flush?0:pop;d.eval();
  assert(d.occupancy==(EXPECT_DUAL?q.size():0));assert(bool(d.d_valid)==(!flush&&available!=0));
  if(d.d_valid){assert(d.d_packet==(q.empty()?packet:q.front()));bool second=EXPECT_DUAL&&available>=2;assert(bool(d.second_valid)==second);if(second)assert(d.second_packet==(q.size()>=2?q[1]:packet));}
  bool push=uv&&d.u_ready;
  if(flush)q.clear();else if(EXPECT_DUAL){if(push)q.push_back(packet);for(unsigned i=0;i<pop;++i){assert(!q.empty());q.pop_front();}assert(q.size()<=2);pairs+=pop==2;exchanges+=push&&pop==2;}
  d.clk=1;d.eval();assert(d.occupancy==(EXPECT_DUAL?q.size():0));
 }
 assert(!EXPECT_DUAL||pairs>1000);std::cout<<"ISSUE PAIR QUEUE MODEL PASS: 50000 cycles, enabled="<<EXPECT_DUAL<<", pair_pops="<<pairs<<", pair_pop_push="<<exchanges<<"\n";
}
