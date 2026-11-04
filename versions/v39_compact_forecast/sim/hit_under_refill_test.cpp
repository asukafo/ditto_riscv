#include "Vrv64_icache.h"
#include "verilated.h"
#include <cassert>
#include <cstdint>
#include <deque>
#include <iostream>
#ifndef EXPECT_UNDER
#define EXPECT_UNDER 1
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
int main(){unsigned checks=0;
 // Critical response, then multiple ordered warm hits without waiting for remainder.
 for(bool waiting:{false,true})for(unsigned size:{1u,2u}){
  Cache c;c.warm(0x20);c.warm(0x40);c.background(waiting);unsigned before=c.requests;
  c.input(0x22,size);assert(bool(c.d.u_ready)==bool(EXPECT_UNDER));c.edge();
  if(EXPECT_UNDER){assert(c.accepted);if(!waiting)assert(c.returned&&c.data==Cache::word(0x80,2));c.input(0x44);c.edge();assert(c.accepted&&c.returned&&c.data==Cache::word(0x22,size)&&!c.error);c.d.u_valid=0;c.edge();assert(c.returned&&c.data==Cache::word(0x44,2)&&!c.error);assert(c.refill_hits==2);}
  else{assert(!c.accepted);c.d.u_valid=0;c.edge();assert(c.refill_hits==0);}
  assert(c.requests==before);c.finish();++checks;
 }
 // The final success/error and a younger accepted hit may coincide.
 for(bool err:{false,true}){
  Cache c;c.warm(0x20);c.background(true);c.input(0x24);c.response(err);assert(bool(c.d.u_ready)==bool(EXPECT_UNDER));c.edge();c.clear_response();c.d.u_valid=0;c.eval();
  if(EXPECT_UNDER){assert(c.d.u_rsp_valid&&!c.d.u_rsp_error&&c.d.u_rsp_data==Cache::word(0x24,2));c.edge();assert(c.returned&&!c.error);}
  else assert(!c.d.u_rsp_valid);
  assert(c.memory.empty());++checks;
 }
 // Backpressure on old critical word blocks younger hits; a held younger hit survives final beat.
 for(bool err:{false,true}){
  Cache c;c.warm(0x20);c.background(false);c.d.u_rsp_ready=0;c.input(0x24);
  for(unsigned i=0;i<4;++i){c.eval();assert(!c.d.u_ready&&c.d.u_rsp_valid&&c.d.u_rsp_data==Cache::word(0x80,2));c.edge();}
  c.d.u_rsp_ready=1;c.eval();assert(bool(c.d.u_ready)==bool(EXPECT_UNDER));c.edge();c.d.u_valid=0;c.d.u_rsp_ready=0;c.d.d_ready=1;c.edge();assert(c.memory.size()==1);c.response(err);c.edge();c.clear_response();
  if(EXPECT_UNDER){for(unsigned i=0;i<4;++i){assert(c.d.u_rsp_valid&&c.d.u_rsp_data==Cache::word(0x24,2)&&!c.d.u_rsp_error);c.edge();}c.d.u_rsp_ready=1;c.edge();assert(c.returned&&!c.error);}
  else assert(!c.d.u_rsp_valid);
  ++checks;
 }
 // Invalidate disables hits and the old remainder must not validate its line.
 for(bool waiting:{false,true}){
  Cache c;c.warm(0x20);c.background(waiting);c.input(0x20);c.d.invalidate=1;c.eval();assert(!c.d.u_ready&&!c.d.refill_hit_event);c.edge();c.d.invalidate=0;c.finish();
  unsigned before=c.requests;c.warm(0x80);assert(c.requests==before+2);++checks;
 }
 // No partially valid line, conflict victim, second miss, or bypass may pass during refill.
 for(uint64_t a:{0x84ULL,0x180ULL,0x600ULL,0x10020ULL,0x0200bff8ULL}){
  Cache c;c.warm(0x20);c.background(true);c.input(a);assert(!c.d.u_ready&&!c.d.refill_hit_event);c.edge();assert(!c.accepted);c.finish();++checks;
 }
 for(unsigned operation:{0u,1u,2u}){
  Cache c;c.warm(0x20);c.background(true);c.input(0x20);c.d.u_execute=operation!=0;c.d.u_write=operation==1;c.d.u_atomic=operation==2;c.eval();assert(!c.d.u_ready);c.edge();assert(!c.accepted);c.d.u_write=0;c.d.u_atomic=0;c.d.u_execute=1;c.finish();++checks;
 }
 // Before the critical beat no younger response can pass it.
 {
  Cache c;c.warm(0x20);c.start(0x80);c.input(0x20);assert(!c.d.u_ready);c.edge();assert(!c.accepted);c.d.u_valid=0;c.response();c.edge();c.clear_response();c.finish();++checks;
 }
 // A conflicting miss invalidates the warm index immediately.
 {
  Cache c;c.warm(0x20);c.start(0x120);c.response();c.edge();c.clear_response();c.d.d_ready=0;c.input(0x20);assert(!c.d.u_ready);c.edge();assert(!c.accepted);c.finish();++checks;
 }
 std::cout<<"HIT UNDER REFILL UNIT PASS: "<<checks<<" cases, enabled="<<EXPECT_UNDER<<"; ordered hits/backpressure/final success-error/invalidation/conflicts/bypass/single physical request\n";
}
