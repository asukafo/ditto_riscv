#include "Vrv64_fetch_window.h"
#include "verilated.h"
#include <cassert>
#include <cstdint>
#include <deque>
#include <iostream>
#ifndef EXPECT_ISSUE
#define EXPECT_ISSUE 1
#endif
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
int main(){unsigned cases=0;
 for(uint64_t addr:{0x100ULL,0x102ULL,0x100000102ULL,0xffeULL})for(unsigned size:{1u,2u})for(bool ready:{false,true}){
  Model m;m.request(addr,size,ready);
  if(!ready){for(unsigned i=0;i<3;++i){assert(m.d.d_valid&&m.d.d_addr==addr&&m.d.d_size==size);assert(m.pending.empty());m.edge();}}
  m.finish_send(addr,size);m.d.d_ready=0;m.response(0x12345678);m.check_data(0x12345678);m.edge();m.d.d_rsp_valid=0;m.eval();assert(!m.d.u_rsp_valid);assert(m.sent==1&&m.received==1);++cases;
 }
 for(bool error:{false,true}){
  Model m;m.request(0x102,1);m.finish_send(0x102,1);m.response(0x55aa,error);m.check_data(0x55aa,error);
  m.d.u_valid=1;m.d.u_addr=0x202;m.d.u_size=1;m.eval();assert(m.d.u_ready);assert(bool(m.d.d_valid)==bool(EXPECT_ISSUE));
  if(EXPECT_ISSUE)assert(m.d.d_addr==0x202);m.edge();m.d.u_valid=0;m.d.d_rsp_valid=0;m.eval();
  m.finish_send(0x202,1);m.response(0xbeef);m.check_data(0xbeef);m.edge();m.d.d_rsp_valid=0;m.eval();assert(!m.d.u_rsp_valid&&m.sent==2&&m.received==2);++cases;
 }
 // Accepted old request is poisoned, not cancelled at the service boundary.
 {
  Model m;m.request(0x102,1);m.finish_send(0x102,1);m.d.flush=1;m.d.u_rsp_ready=0;m.edge();m.d.flush=0;m.d.u_rsp_ready=1;m.eval();assert(m.d.u_rsp_valid&&m.d.u_rsp_error);m.edge();
  m.request(0x302,1);m.d.d_ready=1;m.eval();if(m.pending.size()==1){assert(m.d.d_valid&&m.d.d_addr==0x302);m.edge();}
  assert(m.pending.size()==2&&m.pending.front().addr==0x102);m.response(0xdead);assert(m.d.drop_event&&!m.d.u_rsp_valid);m.edge();
  m.response(0xcafe,true);m.check_data(0xcafe,true);m.edge();m.d.d_rsp_valid=0;m.eval();assert(m.pending.empty()&&!m.d.u_rsp_valid);++cases;
 }
 for(bool flush:{false,true}){
  Model m;m.d.u_valid=1;m.d.u_addr=0x102;m.d.u_size=1;m.d.flush=flush;m.d.allow=flush;m.eval();assert(!m.d.u_ready&&!m.d.d_valid);m.edge();assert(m.pending.empty());++cases;
 }
 std::cout<<"DEMAND ISSUE UNIT PASS: "<<cases<<" cases, enabled="<<EXPECT_ISSUE<<"; address/size/backpressure/turnover/error/flush/poison\n";
}
