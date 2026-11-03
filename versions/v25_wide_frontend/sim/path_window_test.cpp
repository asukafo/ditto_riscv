#include "Vrv64_fetch_window.h"
#include "verilated.h"
#include <deque>
#include <map>
#include <vector>
#include <cassert>
#include <cstdint>
#include <iostream>
struct Req{uint64_t addr;unsigned size,due;};
struct Memory{
 Vrv64_fetch_window d;std::deque<Req> pending;std::map<uint64_t,uint32_t> words;std::vector<uint64_t> reads;
 bool accepted=false,responded=false,response_error=false;uint64_t response_data=0,response_cause=0;
 unsigned cycle=0,latency,gap,redirects=0,rejects=0,blocks=0;uint64_t fail=~uint64_t(0);
 Memory(unsigned l,unsigned g):latency(l),gap(g){d.clk=0;d.reset=1;d.flush=0;d.allow=1;d.u_valid=0;d.u_rsp_ready=1;d.d_ready=0;d.d_rsp_valid=0;d.predictor_clear=0;d.btb_train=0;d.bht_train=0;d.train_taken=0;d.train_index=0;d.train_pc=0;d.train_next=0;d.train_bytes=4;d.train_insn=0;d.ras_valid=0;d.ras_target=0;d.eval();d.clk=1;d.eval();d.reset=0;}
 void tick(){d.clk=0;d.d_ready=pending.size()<4&&cycle%(gap+1)==0;d.d_rsp_valid=!pending.empty()&&pending.front().due<=cycle;
  if(d.d_rsp_valid){auto r=pending.front();d.d_rsp_data=words.count(r.addr)?words[r.addr]:0x13;d.d_rsp_error=r.addr==fail;d.d_rsp_cause=d.d_rsp_error?12:1;}
  d.eval();accepted=d.u_valid&&d.u_ready;responded=d.u_rsp_valid&&d.u_rsp_ready;response_data=d.u_rsp_data;response_cause=d.u_rsp_cause;response_error=d.u_rsp_error;
  bool send=d.d_valid&&d.d_ready,returned=d.d_rsp_valid&&d.d_rsp_ready;Req request{d.d_addr,unsigned(d.d_size),cycle+latency};
  if(!pending.empty()&&request.due<=pending.back().due)request.due=pending.back().due+1;
  redirects+=d.path_redirect_event;rejects+=d.path_reject_event;blocks+=d.path_page_block_event;
  if(send)reads.push_back(request.addr);d.clk=1;d.eval();++cycle;if(returned)pending.pop_front();if(send)pending.push_back(request);
 }
 void train(uint32_t insn,uint64_t target,unsigned bytes=4){d.btb_train=1;d.train_pc=0;d.train_next=target;d.train_insn=insn;d.train_bytes=bytes;tick();d.btb_train=0;}
 bool requested(uint64_t a){for(auto pc:reads)if(pc==a)return true;return false;}
 void read(uint64_t addr,bool error=false){d.u_valid=1;d.u_addr=addr;d.u_size=2;
  for(unsigned i=0;;++i){assert(i<2000);tick();if(accepted)break;}
  d.u_valid=0;
  for(unsigned i=0;;++i){assert(i<2000);tick();
   if(responded){assert(response_error==error);if(error)assert(response_cause==12);else assert(response_data==(words.count(addr)?words[addr]:0x13));break;}
  }
 }
};
int main(){unsigned checks=0;
 for(auto cfg:{std::pair<unsigned,unsigned>{1,0},{5,3},{20,7}}){
  {Memory m(cfg.first,cfg.second);m.words[0]=0x000300e7;m.train(m.words[0],64);m.read(0);m.tick();assert(m.requested(64)&&!m.requested(4));m.read(64);assert(m.redirects>0&&m.rejects==0);++checks;}
  {Memory m(cfg.first,cfg.second);m.words[0]=0x00008067;m.d.ras_valid=1;m.d.ras_target=64;m.train(m.words[0],128);m.read(0);m.tick();assert(m.requested(64)&&!m.requested(128));m.read(64);assert(m.rejects==0);++checks;}
  {Memory m(cfg.first,cfg.second);m.words[0]=0x00000463;m.train(m.words[0],8);m.read(0);m.tick();assert(m.requested(4));m.read(4);assert(m.redirects==0&&m.rejects==0);++checks;}
  {Memory m(cfg.first,cfg.second);m.words[0]=0x000300e7;m.train(m.words[0],0x1000);m.read(0);m.tick();assert(m.blocks>0&&!m.requested(0x1000));m.read(4);++checks;}
  {Memory m(cfg.first,cfg.second);m.words[0]=0x0100006f;m.train(0x0080006f,8);m.read(0);m.tick();assert(m.requested(8)&&m.rejects>0);m.read(16);++checks;}
  {Memory m(cfg.first,cfg.second);m.words[0]=0x00150513;m.train(0x000300e7,64);m.read(0);m.tick();assert(m.rejects>0);m.read(4);++checks;}
  {Memory m(cfg.first,cfg.second);m.words[0]=0x0001a011;m.train(0x0080006f,8);m.read(0);m.tick();assert(m.rejects>0);m.read(4);++checks;}
  {Memory m(cfg.first,cfg.second);m.words[0]=0x000300e7;m.fail=0;m.train(m.words[0],64);m.read(0,true);m.tick();assert(m.rejects>0);++checks;}
 }
 std::cout<<"PATH WINDOW DIRECTED PASS: "<<checks<<" cases, target/RAS/cold-direction/page/type/length/fault checks\n";
}
