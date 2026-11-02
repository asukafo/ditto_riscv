#include "Vrv64_fetch_window.h"
#include "verilated.h"
#include <deque>
#include <cassert>
#include <cstdint>
#include <iostream>
struct Read{uint64_t address;unsigned size,due;};
uint64_t value(uint64_t a,unsigned s){uint64_t x=(a*0x9e3779b97f4a7c15ULL)^0x123456789abcdef0ULL;return s==1?x&65535:x&0xffffffff;}
int main(){Vrv64_fetch_window d;std::deque<Read> memory;uint64_t rng=0x44aa11;bool pending=false,cancel=false,source=false;uint64_t expected=0,addr=0;unsigned size=2,expected_size=2,peak=0,consumed=0,drops=0;
 auto random=[&](){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;return rng;};
 d.clk=0;d.reset=1;d.flush=0;d.allow=0;d.u_valid=0;d.u_rsp_ready=0;d.d_ready=0;d.d_rsp_valid=0;d.eval();d.clk=1;d.eval();d.reset=0;
 for(unsigned cycle=0;cycle<40000;++cycle){
  auto bits=random();bool flush=cycle%89>=40 && cycle%89<=42;bool ready=(bits&7)!=0;
  if(flush)source=false;
  if(!source && !pending){source=true;addr=(bits&1)?((bits>>4)&0x3fc):((addr+4)&0x3fc);if((bits&63)==7)addr=0xffc;size=(bits&31)==3?1:2;}
  d.clk=0;d.flush=flush;d.allow=cycle%53<49;d.u_valid=source;d.u_addr=addr;d.u_size=size;d.u_rsp_ready=ready;d.d_ready=memory.size()<4 && (bits&15)!=0;
  bool returned=!memory.empty()&&memory.front().due<=cycle;d.d_rsp_valid=returned;
  if(returned){d.d_rsp_data=value(memory.front().address,memory.front().size);d.d_rsp_error=memory.front().address==0xffc;d.d_rsp_cause=d.d_rsp_error?12:1;}
  d.eval();if(flush && pending)cancel=true;
  bool consume=d.u_rsp_valid&&ready,accept=source&&d.u_ready,send=d.d_valid&&d.d_ready,response=returned&&d.d_rsp_ready;
  if(consume){assert(pending);if(!cancel){assert(bool(d.u_rsp_error)==(expected==0xffc));if(expected==0xffc)assert(d.u_rsp_cause==12);assert(d.u_rsp_data==value(expected,expected_size));}pending=false;cancel=false;++consumed;}
  if(accept){assert(!pending);pending=true;cancel=false;expected=addr;expected_size=size;source=false;}
  if(send)assert(d.d_addr<0x1000);
  Read next{d.d_addr,unsigned(d.d_size),cycle+7};if(!memory.empty() && next.due<=memory.back().due)next.due=memory.back().due+1;
  drops+=d.drop_event;assert(d.pending<=4);if(d.pending>peak)peak=d.pending;
  d.clk=1;d.eval();if(response)memory.pop_front();if(send)memory.push_back(next);
 }
 assert(consumed>500&&peak>=2&&drops>0);
 std::cout<<"FETCH WINDOW MODEL PASS: 40000 cycles, responses="<<consumed<<", peak="<<peak<<", poisoned="<<drops<<"\n";
}
