#include "Vrv64_icache.h"
#include "verilated.h"
#include <cassert>
#include <cstdint>
#include <deque>
#include <iostream>
#ifndef EXPECT_FILL
#define EXPECT_FILL 1
#endif
struct Req{uint64_t addr;unsigned size;};
struct Cache{
 Vrv64_icache d;std::deque<Req> memory;unsigned requests=0,refill_hits=0;bool accepted=false,returned=false;uint64_t data=0;bool error=false;
 static uint64_t word(uint64_t a,unsigned size){uint64_t x=0;for(unsigned i=0;i<(1u<<size);++i)x|=uint64_t(uint8_t((a+i)*37+3))<<(8*i);return x;}
 void eval(){d.clk=0;d.eval();}
 void edge(){eval();accepted=d.u_valid&&d.u_ready;returned=d.u_rsp_valid&&d.u_rsp_ready;data=d.u_rsp_data;error=d.u_rsp_error;
  bool send=d.d_valid&&d.d_ready,back=d.d_rsp_valid&&d.d_rsp_ready;Req req{d.d_addr,unsigned(d.d_size)};refill_hits+=d.refill_hit_event;
  if(back){assert(!memory.empty());memory.pop_front();}if(send){assert(memory.empty());memory.push_back(req);++requests;assert(!d.d_write&&!d.d_atomic&&d.d_size==3);}
  d.clk=1;d.eval();eval();
 }
 Cache(){d.clk=0;d.reset=1;d.invalidate=0;d.u_valid=0;d.u_rsp_ready=1;d.u_addr=0;d.u_data=0;d.u_size=2;d.u_write=0;d.u_execute=1;d.u_atomic=0;d.u_amo=0;d.d_ready=1;d.d_rsp_valid=0;d.d_rsp_data=0;d.d_rsp_error=0;eval();edge();d.reset=0;eval();}
 void input(uint64_t a,unsigned size=2){d.u_addr=a;d.u_size=size;d.u_valid=1;eval();}
 void start(uint64_t a){d.d_ready=1;input(a);assert(d.u_ready);edge();assert(accepted);d.u_valid=0;edge();assert(memory.size()==1);}
 void response(bool err=false){assert(!memory.empty());d.d_rsp_valid=1;d.d_rsp_data=word(memory.front().addr,memory.front().size);d.d_rsp_error=err;eval();}
 void clear_response(){d.d_rsp_valid=0;d.d_rsp_error=0;eval();}
 void warm(uint64_t a){start(a);response();edge();clear_response();edge();assert(returned&&!error&&data==word(a,2));assert(memory.size()==1);response();edge();clear_response();assert(memory.empty()&&!d.u_rsp_valid);}
 void background(bool waiting){start(0x80);response();edge();clear_response();d.d_ready=0;
  if(waiting){d.d_ready=1;edge();assert(returned&&!error&&data==word(0x80,2)&&memory.size()==1);d.d_ready=0;}
 }
 void finish(){d.u_valid=0;d.u_rsp_ready=1;d.d_ready=1;eval();if(memory.empty()){assert(d.d_valid);edge();}response();edge();clear_response();for(unsigned i=0;i<3;++i)edge();assert(memory.empty()&&!d.u_rsp_valid);}
};

void background_at(Cache &c,uint64_t a,bool waiting){c.start(a);c.response();c.edge();c.clear_response();c.d.d_ready=0;if(waiting){c.d.d_ready=1;c.edge();assert(c.returned&&!c.error&&c.data==Cache::word(a,2));c.d.d_ready=0;}}
int main(){unsigned cases=0;
 for(uint64_t miss:{0x80ULL,0x8cULL})for(bool waiting:{false,true})for(auto r:{std::pair<unsigned,unsigned>{0,2},{2,1},{4,2},{6,1}}){
  Cache c;background_at(c,miss,waiting);uint64_t addr=(miss&~7ULL)+r.first;unsigned before=c.requests;c.input(addr,r.second);
  assert(bool(c.d.u_ready)==bool(EXPECT_FILL));assert(bool(c.d.fill_hit_event)==bool(EXPECT_FILL));c.edge();c.d.u_valid=0;
  if(EXPECT_FILL){assert(c.accepted);c.edge();assert(c.returned&&!c.error&&c.data==Cache::word(addr,r.second));}
  else assert(!c.accepted);
  assert(c.requests==before);c.finish();++cases;
 }
 for(bool error:{false,true})for(bool hold:{false,true}){
  Cache c;background_at(c,0x8c,true);c.input(0x88);c.response(error);assert(bool(c.d.u_ready)==bool(EXPECT_FILL));c.edge();c.clear_response();c.d.u_valid=0;c.d.u_rsp_ready=!hold;c.eval();
  if(EXPECT_FILL){for(unsigned i=0;i<(hold?4u:1u);++i){assert(c.d.u_rsp_valid&&!c.d.u_rsp_error&&c.d.u_rsp_data==Cache::word(0x88,2));c.edge();}if(hold){c.d.u_rsp_ready=1;c.edge();}assert(c.returned&&!c.error);}
  else assert(!c.d.u_rsp_valid);
  ++cases;
 }
 for(bool waiting:{false,true}){
  Cache c;background_at(c,0x80,waiting);c.input(0x84);c.d.invalidate=1;c.eval();assert(!c.d.u_ready&&!c.d.fill_hit_event);c.edge();c.d.invalidate=0;c.finish();unsigned before=c.requests;c.warm(0x80);assert(c.requests==before+2);++cases;
 }
 for(uint64_t addr:{0x86ULL,0x88ULL,0x180ULL,0x10080ULL}){
  Cache c;background_at(c,0x80,true);c.input(addr,2);assert(!c.d.u_ready&&!c.d.fill_hit_event);c.edge();c.finish();++cases;
 }
 for(unsigned op:{0u,1u,2u}){
  Cache c;background_at(c,0x80,true);c.input(0x84);c.d.u_execute=op!=0;c.d.u_write=op==1;c.d.u_atomic=op==2;c.eval();assert(!c.d.u_ready);c.edge();c.d.u_execute=1;c.d.u_write=0;c.d.u_atomic=0;c.finish();++cases;
 }
 {Cache c;c.start(0x80);c.input(0x84);c.eval();assert(!c.d.u_ready);c.response(true);c.edge();c.clear_response();c.d.u_valid=0;c.eval();assert(c.d.u_rsp_valid&&c.d.u_rsp_error&&!c.d.fill_hit_event);c.edge();++cases;}
 std::cout<<"FILL FORWARD UNIT PASS: "<<cases<<" cases, enabled="<<EXPECT_FILL<<"; both halves/width/order/final error/held response/invalidation/boundary/first fault\n";
}
