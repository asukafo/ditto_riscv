#include "Vrv64_fetch_window.h"
#include "verilated.h"
#include <cassert>
#include <cstdint>
#include <deque>
#include <iostream>
#ifndef EXPECT_PRIORITY
#define EXPECT_PRIORITY 1
#endif
#define EXPECT_ISSUE 1
struct Request{uint64_t addr;unsigned size;};
struct Model{
 Vrv64_fetch_window d;std::deque<Request> pending;unsigned sent=0,received=0;
 void eval(){d.clk=0;d.eval();}
 void edge(){
  eval();bool send=d.d_valid&&d.d_ready,back=d.d_rsp_valid&&d.d_rsp_ready;Request request{d.d_addr,unsigned(d.d_size)};
  if(back){assert(!pending.empty());pending.pop_front();++received;}
  if(send){pending.push_back(request);++sent;}
  d.clk=1;d.eval();eval();assert(d.pending==pending.size());
 }
 Model(){
  d.clk=0;d.reset=1;d.flush=0;d.allow=1;d.predictor_clear=0;d.btb_train=0;d.bht_train=0;d.train_taken=0;d.train_pc=0;d.train_next=0;d.train_insn=0;d.train_bytes=4;d.train_index=0;d.ras_valid=0;d.ras_target=0;
  d.u_valid=0;d.u_addr=0;d.u_size=1;d.u_rsp_ready=1;d.d_ready=1;d.d_rsp_valid=0;d.d_rsp_data=0;d.d_rsp_error=0;d.d_rsp_cause=1;eval();edge();d.reset=0;eval();
 }
 void request(uint64_t addr,unsigned size,bool ready=true){
  d.d_ready=ready;d.u_valid=1;d.u_addr=addr;d.u_size=size;eval();assert(d.u_ready);
  assert(bool(d.d_valid)==bool(EXPECT_ISSUE));if(EXPECT_ISSUE)assert(d.d_addr==addr&&d.d_size==size);edge();d.u_valid=0;eval();
 }
 void finish_send(uint64_t addr,unsigned size){
  d.d_ready=1;eval();if(pending.empty()){assert(d.d_valid&&d.d_addr==addr&&d.d_size==size);edge();}
  assert(pending.size()==1&&pending.front().addr==addr&&pending.front().size==size);
 }
 void response(uint64_t data,bool error=false){assert(!pending.empty());d.d_rsp_valid=1;d.d_rsp_data=data;d.d_rsp_error=error;d.d_rsp_cause=error?12:1;eval();}
 void check_data(uint64_t data,bool error=false){assert(d.u_rsp_valid&&d.u_rsp_data==data&&bool(d.u_rsp_error)==error&&d.u_rsp_cause==(error?12:1));}
};

// Four unsent prefetches: slot order offers 16 before the needed 4/8/12.
void setup(Model &m){
 m.request(0,2);m.finish_send(0,2);m.d.d_ready=0;
 m.edge();m.edge();m.edge(); // allocate 4, 8, 12
 m.response(0x13);m.check_data(0x13);m.edge(); // consumes 0, allocates 16
 m.d.d_rsp_valid=0;m.eval();assert(m.pending.empty());assert(m.d.d_valid&&m.d.d_addr==16);
}
void drain_target(Model &m,uint64_t addr,bool error){
 m.d.d_ready=0;
 while(!m.pending.empty()){
  auto front=m.pending.front();bool target=front.addr==addr;
  m.response(target?0x00700513:0x13,target&&error);
  if(target)m.check_data(0x00700513,error);else assert(!m.d.u_rsp_valid);
  m.edge();m.d.d_rsp_valid=0;m.eval();
 }
 assert(!m.d.u_rsp_valid);
}
int main(){unsigned cases=0,diversions=0;
 for(uint64_t addr:{4ULL,8ULL,12ULL,16ULL})for(unsigned stall:{0u,1u,3u})for(bool error:{false,true}){
  Model m;setup(m);m.d.u_valid=1;m.d.u_addr=addr;m.d.u_size=2;m.d.d_ready=stall==0;m.eval();assert(m.d.u_ready&&m.d.d_valid);
  auto first=EXPECT_PRIORITY?addr:16;assert(m.d.d_addr==first);m.edge();m.d.u_valid=0;m.eval();
  if(stall){for(unsigned i=0;i<stall;++i){assert(m.d.d_valid&&m.d.d_addr==addr);m.edge();}m.d.d_ready=1;m.eval();assert(m.d.d_addr==addr);m.edge();}
  else if(first!=addr){++diversions;assert(m.d.d_addr==addr);m.edge();}
  drain_target(m,addr,error);++cases;
 }
 // Existing in-flight/completed prefetches must not be sent a second time.
 for(bool complete:{false,true}){
  Model m;setup(m);m.d.d_ready=1;m.edge();assert(m.pending.size()==1&&m.pending.front().addr==16);m.d.d_ready=0;
  if(complete){m.response(0x00700513);assert(!m.d.u_rsp_valid);m.edge();m.d.d_rsp_valid=0;}
  m.d.u_valid=1;m.d.u_addr=16;m.d.u_size=2;m.eval();assert(m.d.u_ready);m.edge();m.d.u_valid=0;m.eval();
  if(complete){m.check_data(0x00700513);m.edge();assert(!m.d.u_rsp_valid);}else drain_target(m,16,false);
  assert(m.sent==2&&m.received==2);++cases;
 }
 // Same address, distinct old-poisoned and new owners; old data cannot leak.
 {
  Model m;setup(m);m.d.d_ready=1;m.edge();m.d.d_ready=0;m.d.flush=1;m.edge();m.d.flush=0;m.eval();
  m.request(16,2);assert(m.pending.size()==2);m.d.d_ready=0;m.response(0xdead);assert(m.d.drop_event&&!m.d.u_rsp_valid);m.edge();
  m.response(0x55aa);m.check_data(0x55aa);m.edge();m.d.d_rsp_valid=0;m.eval();assert(m.pending.empty()&&!m.d.u_rsp_valid);++cases;
 }
 for(bool flush:{false,true}){
  Model m;setup(m);m.d.u_valid=1;m.d.u_addr=8;m.d.u_size=2;m.d.d_ready=1;m.d.flush=flush;m.d.allow=flush;m.eval();assert(!m.d.u_ready&&!m.d.d_valid);m.edge();assert(m.pending.empty());++cases;
 }
 assert(diversions==(EXPECT_PRIORITY?0u:6u));
 std::cout<<"DEMAND PRIORITY UNIT PASS: "<<cases<<" cases, enabled="<<EXPECT_PRIORITY<<"; priority/backpressure/error/issued/completed/same-address-poison/flush; diversions="<<diversions<<"\n";
}
