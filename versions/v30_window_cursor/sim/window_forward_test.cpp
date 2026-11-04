#include "Vrv64_fetch_window.h"
#include "verilated.h"
#include <cassert>
#include <cstdint>
#include <iostream>
#ifndef EXPECT_FORWARD
#define EXPECT_FORWARD 1
#endif
struct Test {
 Vrv64_fetch_window d;bool last_sent=false;uint64_t last_addr=0;
 void edge(){last_sent=d.d_valid&&d.d_ready;last_addr=d.d_addr;d.clk=1;d.eval();d.clk=0;d.eval();}
 Test(){
  d.clk=0;d.reset=1;d.flush=0;d.allow=1;d.predictor_clear=0;d.btb_train=0;d.bht_train=0;
  d.train_taken=0;d.train_pc=0;d.train_next=0;d.train_insn=0;d.train_bytes=4;d.train_index=0;d.ras_valid=0;d.ras_target=0;
  d.u_valid=0;d.u_addr=0;d.u_size=1;d.u_rsp_ready=0;d.d_ready=1;d.d_rsp_valid=0;d.d_rsp_data=0;d.d_rsp_error=0;d.d_rsp_cause=0;d.eval();edge();d.reset=0;d.eval();
 }
 void request(uint64_t addr){d.u_valid=1;d.u_addr=addr;d.eval();assert(d.u_ready);edge();d.u_valid=0;d.eval();}
 void sent(uint64_t addr){if(last_sent){assert(last_addr==addr&&d.pending==1);last_sent=false;}else{assert(d.d_valid&&d.d_ready&&d.d_addr==addr);edge();assert(d.pending==1);last_sent=false;}}
 void response(uint64_t data,bool error){d.d_rsp_valid=1;d.d_rsp_data=data;d.d_rsp_error=error;d.d_rsp_cause=error?12:1;d.eval();assert(d.d_rsp_ready);}
 void check(uint64_t data,bool error){assert(d.u_rsp_valid);assert(d.u_rsp_data==data&&bool(d.u_rsp_error)==error&&d.u_rsp_cause==(error?12:1));}
};
int main(){unsigned cases=0;
 for(bool error:{false,true})for(unsigned hold:{0u,1u,7u})for(bool allow:{false,true}){
  Test t;t.request(0x102);t.sent(0x102);t.d.allow=allow;t.d.u_rsp_ready=hold==0;
  uint64_t data=error?0x1234:0x8a5c;t.response(data,error);assert(bool(t.d.u_rsp_valid)==bool(EXPECT_FORWARD));
  if(EXPECT_FORWARD)t.check(data,error);t.edge();t.d.d_rsp_valid=0;t.d.d_rsp_data=0xdead;t.d.d_rsp_error=!error;t.d.d_rsp_cause=99;t.d.eval();
  if(hold || !EXPECT_FORWARD){
   for(unsigned i=0;i<hold;++i){t.check(data,error);t.edge();}
   t.d.u_rsp_ready=1;t.d.eval();t.check(data,error);t.edge();
  }
  assert(!t.d.u_rsp_valid&&t.d.pending==0);++cases;
 }
 // A new demand can replace the just-returned owner on the same clock edge.
 for(bool error:{false,true}){
  Test t;t.request(0x100);t.sent(0x100);t.d.u_rsp_ready=1;t.response(0x55aa,error);
  t.d.u_valid=1;t.d.u_addr=0x202;t.d.eval();assert(bool(t.d.u_ready)==bool(EXPECT_FORWARD));t.edge();
  t.d.d_rsp_valid=0;t.d.eval();if(!EXPECT_FORWARD){t.check(0x55aa,error);assert(t.d.u_ready);t.edge();}
  t.d.u_valid=0;t.d.eval();t.sent(0x202);t.response(0xbeef,false);if(EXPECT_FORWARD)t.check(0xbeef,false);t.edge();
  t.d.d_rsp_valid=0;t.d.eval();if(!EXPECT_FORWARD){t.check(0xbeef,false);t.edge();}assert(!t.d.u_rsp_valid);++cases;
 }
 // Flush with a returning response drains it; repeated flush cannot resurrect it.
 for(bool ready:{false,true}){
  Test t;t.request(0x100);t.sent(0x100);t.d.u_rsp_ready=ready;t.d.flush=1;t.response(0x7788,false);assert(t.d.drop_event);t.edge();
  t.d.d_rsp_valid=0;t.d.eval();t.edge();t.d.flush=0;t.d.u_rsp_ready=1;t.d.eval();
  if(t.d.u_rsp_valid){assert(t.d.u_rsp_error);t.edge();}assert(!t.d.u_rsp_valid&&t.d.pending==0);++cases;
 }
 // Flush before return: a poisoned response must never become demand data.
 {
  Test t;t.request(0x100);t.sent(0x100);t.d.flush=1;t.edge();t.d.flush=0;t.d.u_rsp_ready=1;t.d.eval();assert(t.d.u_rsp_valid&&t.d.u_rsp_error);t.edge();
  t.response(0x9999,false);assert(t.d.drop_event&&!t.d.u_rsp_valid);t.edge();t.d.d_rsp_valid=0;t.d.eval();assert(t.d.pending==0&&!t.d.u_rsp_valid);++cases;
 }
 std::cout<<"WINDOW FORWARD UNIT PASS: "<<cases<<" cases, enabled="<<EXPECT_FORWARD<<"; return/backpressure/error/turnover/flush/poison\n";
}
