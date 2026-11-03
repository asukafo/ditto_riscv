#define main old_icache_main
#include "icache_test.cpp"
#undef main
#include <deque>
#ifndef EXPECT_UNDER
#define EXPECT_UNDER 1
#endif
int main(){
 uint64_t rng=0x32ac44f1;auto random=[&](){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;return rng;};unsigned total=0,under=0;
 for(auto cfg:std::array<std::array<int,2>,3>{{{{1,0}},{{5,3}},{{20,7}}}}){
  Memory m(cfg[0],cfg[1]);std::deque<uint64_t> expected;bool source=false;uint64_t addr=0;unsigned size=2,done=0;
  for(unsigned cycle=0;cycle<40000;++cycle){auto bits=random();
   if(!source && (bits&3)!=0){source=true;addr=(bits>>8)&0x3fe;size=(bits&8)?1:2;}
   m.top.u_valid=source;m.top.u_addr=addr;m.top.u_size=size;m.top.u_rsp_ready=(bits&7)!=0 && cycle%97<85;m.top.invalidate=cycle%211==91;
   auto edge=m.step();under+=edge.refill_hit;
   if(edge.returned){check(!expected.empty()&&!edge.result.error&&edge.result.data==expected.front(),"random response mismatch/order");expected.pop_front();++done;}
   if(edge.accepted){expected.push_back(m.read(addr,size));source=false;}
   check(expected.size()<=1,"response capacity exceeded");
  }
  check(done>500&&m.hits>10,"random model did not progress");total+=done;
 }
 check(EXPECT_UNDER?under>0:under==0,"hit-under-refill mode mismatch");
 std::cout<<"REFILL RANDOM MODEL PASS: 120000 cycles, responses="<<total<<", under_events="<<under<<", enabled="<<EXPECT_UNDER<<"; independent byte/order/backpressure/invalidation/single downstream checks\n";
}
