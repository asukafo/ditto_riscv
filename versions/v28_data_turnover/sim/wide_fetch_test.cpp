#include "Vrv64_fetch.h"
#include "verilated.h"
#include <array>
#include <vector>
#include <random>
#include <iostream>
#include <stdexcept>
static void ck(bool b,const char* m){if(!b)throw std::runtime_error(m);}
struct Insn{uint64_t pc,next,value,cause;uint32_t raw,insn;unsigned bytes;bool fault,illegal;bool operator==(const Insn& b)const{return pc==b.pc&&next==b.next&&value==b.value&&cause==b.cause&&raw==b.raw&&insn==b.insn&&bytes==b.bytes&&fault==b.fault&&illegal==b.illegal;}};
struct Harness{
 Vrv64_fetch d;std::array<uint8_t,8192> mem{};std::vector<Insn> got;std::vector<std::pair<uint64_t,unsigned>> reqs;std::vector<Insn> held;std::mt19937 rng{25};unsigned latency,gap,ticks=0,left=0,pairs=0,partial=0;bool pending=false,error=false;uint64_t data=0,fail=~0ULL;
 Harness(unsigned l,unsigned g):latency(l),gap(g){for(unsigned i=0;i<mem.size();i+=2)put(i,1,2);d.clk=0;d.reset=1;d.eval();d.clk=1;d.eval();d.reset=0;}
 void put(unsigned a,uint32_t v,unsigned n){for(unsigned i=0;i<n;i++)mem.at(a+i)=v>>(8*i);}
 uint64_t bits(unsigned low,unsigned n){uint64_t v=0;for(unsigned i=0;i<n;i++)v|=uint64_t((d.second_packet[(low+i)/32]>>((low+i)%32))&1)<<i;return v;}
 std::vector<Insn> packets(){std::vector<Insn> a;if(d.valid)a.push_back({d.pc,d.predicted_next,d.fault_value,d.fault_cause,d.raw_insn,d.insn,d.bytes,bool(d.fetch_fault),bool(d.illegal)});if(d.second_valid){ck(d.valid,"second without first");a.push_back({bits(269,64),bits(205,64),bits(77,64),bits(141,64),uint32_t(bits(13,32)),uint32_t(bits(45,32)),unsigned(bits(10,3)),bool(bits(8,1)),bool(bits(9,1))});}return a;}
 void step(unsigned slots){d.clk=0;d.ready=slots!=0;d.ready_slots=slots;d.req_ready=!pending&&ticks%(gap+1)==0;d.rsp_valid=pending&&left==0;d.rsp_data=data;d.rsp_error=error;d.rsp_cause=12;d.eval();auto out=packets();if(!d.redirect&&!held.empty()){ck(out.size()>=held.size(),"held bundle disappeared");for(unsigned i=0;i<held.size();i++)ck(out[i]==held[i],"held metadata changed");}
 unsigned take=d.redirect?0:std::min<unsigned>(slots,out.size());if(take==1&&out.size()==2)partial++;for(unsigned i=0;i<take;i++)got.push_back(out[i]);held.clear();if(!d.redirect)for(unsigned i=take;i<out.size();i++)held.push_back(out[i]);
 bool send=d.req_valid&&d.req_ready,ret=d.rsp_valid&&d.rsp_ready;uint64_t addr=d.req_addr;unsigned size=d.req_size;pairs+=d.decode_pair_event;d.clk=1;d.eval();ticks++;if(ret)pending=false;if(send){ck(!pending,"multiple outstanding requests");reqs.emplace_back(addr,size);ck((addr&4095)+(1u<<size)<=4096,"request crossed page");data=0;for(unsigned i=0;i<(1u<<size);i++)data|=uint64_t(mem.at(addr+i))<<(8*i);error=addr==fail;pending=true;left=latency-1;}else if(pending&&left)left--;}
 void collect(unsigned n){unsigned target=got.size()+n;for(unsigned k=0;k<20000&&got.size()<target;k++)step(std::min<unsigned>(target-got.size(),rng()%3));ck(got.size()==target,"collection timeout");}
 void redirect(uint64_t pc){d.redirect=1;d.redirect_pc=pc;step(0);d.redirect=0;got.clear();held.clear();}
};
int main(){try{unsigned checks=0,pairs=0,partial=0;for(auto cfg:std::array<std::array<unsigned,2>,3>{{{{1,0}},{{5,3}},{{20,7}}}}){
 {Harness h(cfg[0],cfg[1]);std::vector<Insn> expected;unsigned a=0;std::mt19937 rng(77);for(unsigned i=0;i<160;i++){unsigned n=rng()%2?2:4;uint32_t raw=n==2?1:0x00150513;h.put(a,raw,n);expected.push_back({a,a+n,0,0,raw,n==2?0x13:raw,n,false,false});a+=n;}h.collect(expected.size());ck(h.got==expected,"mixed-length instruction stream");ck(h.reqs[0].second==3,"no 64-bit word fetch");pairs+=h.pairs;partial+=h.partial;checks+=160;}
 for(bool fault:{false,true}){Harness h(cfg[0],cfg[1]);h.put(0xffe,0x02a00513,4);if(fault)h.fail=0x1000;h.redirect(0xff8);h.collect(4);ck(h.got[0].pc==0xff8&&h.got[2].pc==0xffc&&!h.got[2].fault,"older legal instruction lost before fault");auto x=h.got[3];ck(x.pc==0xffe&&x.bytes==4,"cross-page PC/length");if(fault)ck(x.fault&&x.value==0x1000&&x.cause==12,"cross-page fault attribution");else ck(!x.fault&&x.raw==0x02a00513,"cross-page assembly");checks+=3;}
 {Harness h(cfg[0],cfg[1]);h.put(0,0x00150513,4);h.put(4,0x0080006f,4);h.put(8,0,4);h.put(12,0x00700513,4);for(unsigned i=0;i<1000&&!h.d.valid;i++)h.step(0);ck(h.d.second_valid,"direct jump was not emitted in the second slot");h.collect(3);ck(h.got[0].pc==0&&h.got[1].pc==4&&h.got[1].next==12&&h.got[2].pc==12,"second-slot jump target and sequential tail discard");checks++;}
 {Harness h(cfg[0],cfg[1]);h.put(0,0x0080006f,4);h.put(4,0,4);h.put(8,0x00700513,4);h.collect(2);ck(h.got[0].pc==0&&h.got[1].pc==8,"predicted taken leaked sequential second");checks++;}
 {Harness h(cfg[0],cfg[1]);h.put(0,0x00150513,4);h.put(4,0x00258593,4);for(unsigned i=0;i<1000&&!h.d.valid;i++)h.step(0);h.step(1);ck(h.got.size()==1&&h.d.valid&&!h.d.second_valid,"partial bundle consumption");h.put(64,0x00700513,4);h.redirect(64);h.collect(1);ck(h.got[0].pc==64&&h.got[0].raw==0x00700513,"redirect left partial bundle alive");checks++;}
 {Harness h(cfg[0],cfg[1]);for(unsigned i=0;i<1000&&!h.pending;i++)h.step(0);h.put(64,0x00700513,4);h.redirect(64);h.collect(1);ck(h.got[0].pc==64,"redirect failed to drain old response");checks++;}
 }ck(pairs&&partial,"missing pair/partial coverage");std::cout<<"WIDE FETCH PASS: "<<checks<<" checks; pairs="<<pairs<<", partial accepts="<<partial<<"; 3 latency/backpressure configurations\n";return 0;}catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}}
