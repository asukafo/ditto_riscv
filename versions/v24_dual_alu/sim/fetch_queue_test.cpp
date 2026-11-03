#include "Vrv64_fetch_queue.h"
#include "verilated.h"
#include <array>
#include <cassert>
#include <cstdint>
#include <deque>
#include <iostream>
#ifndef EXPECT_ENABLE
#define EXPECT_ENABLE 1
#endif
int main(){Vrv64_fetch_queue d;using Packet=std::array<uint32_t,11>;std::deque<Packet> queue;
 uint64_t rng=0xaabbccdd;unsigned steps=0,full_exchange=0,flush_full=0,bypasses=0;
 auto random=[&](){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;return rng;};
 auto step=[&](bool valid,bool ready,bool flush,bool reset){
  Packet packet{};for(auto& word:packet)word=random();packet[10]&=0x1fff;
  d.clk=0;d.u_valid=valid;d.d_ready=ready;d.flush=flush;d.reset=reset;
  for(unsigned i=0;i<11;++i)d.u_packet[i]=packet[i];d.eval();
  bool running=!flush && !reset;bool ur=running&&(EXPECT_ENABLE ? queue.size()<4 || ready : ready);
  bool dv=running&&(!queue.empty() || valid);assert(bool(d.u_ready)==ur);assert(bool(d.d_valid)==dv);assert(d.occupancy==queue.size());
  if(dv){const Packet& expected=queue.empty()?packet:queue.front();for(unsigned i=0;i<11;++i)assert(d.d_packet[i]==expected[i]);}
  bool push=EXPECT_ENABLE&&valid&&ur&&!(queue.empty()&&ready),pop=EXPECT_ENABLE&&running&&!queue.empty()&&ready;
  assert(bool(d.push_event)==push);assert(bool(d.pop_event)==pop);
  assert(bool(d.bypass_event)==bool(EXPECT_ENABLE&&running&&queue.empty()&&valid&&ready));
  assert(bool(d.full_stall)==bool(EXPECT_ENABLE&&running&&queue.size()==4&&valid&&!ready));
  assert(bool(d.flush_event)==bool(EXPECT_ENABLE&&!reset&&flush&&!queue.empty()));
  full_exchange+=queue.size()==4&&push&&pop;flush_full+=queue.size()==4&&flush;
  bypasses+=d.bypass_event;
  if(reset||flush||!EXPECT_ENABLE)queue.clear();else{if(pop)queue.pop_front();if(push)queue.push_back(packet);}
  d.clk=1;d.eval();assert(d.occupancy==queue.size());++steps;
 };
 step(0,0,0,1);
 for(unsigned round=0;round<20;++round){for(unsigned i=0;i<5;++i)step(1,0,0,0);for(unsigned i=0;i<12;++i)step(1,1,0,0);step(1,1,1,0);step(1,1,0,0);}
 for(unsigned i=0;i<30000;++i){auto f=random();step(f&1,f&2,(f&127)==0,(f&1023)==1);}
 if(EXPECT_ENABLE)assert(full_exchange>100&&flush_full>0&&bypasses>100);
 std::cout<<"FETCH QUEUE MODEL PASS: "<<steps<<" steps, enabled="<<EXPECT_ENABLE<<", full exchange="<<full_exchange<<", full flush="<<flush_full<<"\n";
}
