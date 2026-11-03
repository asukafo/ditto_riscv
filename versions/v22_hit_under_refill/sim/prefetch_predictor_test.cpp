#include "Vrv64_prefetch_predictor.h"
#include "verilated.h"
#include <array>
#include <cassert>
#include <cstdint>
#include <iostream>
#ifndef EXPECT_ENABLE
#define EXPECT_ENABLE 1
#endif
struct Entry{bool valid=false;uint64_t pc=0,target=0;unsigned kind=0,bytes=0;bool backward=false;};
int main(){Vrv64_prefetch_predictor d;std::array<Entry,32> table{};std::array<unsigned,32> counters{};std::array<bool,32> valid{};unsigned history=0,steps=0;uint64_t rng=0xaaccee11;
 auto random=[&](){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;return rng;};
 auto step=[&](uint64_t pc,uint64_t w,uint32_t insn,uint64_t next,unsigned bytes,bool bt,bool dh,bool taken,unsigned index,bool clear,bool reset,bool rv,uint64_t rt){
  d.clk=0;d.pc=pc;d.train_pc=w;d.train_insn=insn;d.train_next=next;d.train_bytes=bytes;d.btb_train=bt;d.bht_train=dh;d.train_taken=taken;d.train_index=index;d.clear=clear;d.reset=reset;d.ras_valid=rv;d.ras_target=rt;d.eval();
  auto check=[&](){Entry e=table[(pc>>1)&31];bool hit=EXPECT_ENABLE && !(pc&1) && e.valid && e.pc==pc;unsigned kind=hit?e.kind:0;
   unsigned idx=((pc>>1)&31)^history;bool tk=kind!=1 || (valid[idx]?counters[idx]>=2:e.backward);
   uint64_t target=kind==3 && rv?rt:e.target;bool eligible=hit && !(pc&3) && (e.bytes==2 || e.bytes==4);
   bool same=(target>>12)==(pc>>12),hint=eligible&&(!tk || (!(target&3)&&same));
   assert(bool(d.hint)==hint);assert(bool(d.page_block)==bool(eligible&&tk&&!same));assert(d.next_pc==(hint&&tk?target:pc+4));
   assert(d.kind==kind && d.bytes==(hit?e.bytes:0) && d.target==(hit?e.target:0));};check();
  if(reset || clear || !EXPECT_ENABLE){table={};valid.fill(false);counters.fill(1);history=0;}
  else{
   if(dh){counters[index]=!valid[index]?(taken?2:1):taken?(counters[index]<3?counters[index]+1:3):(counters[index]?counters[index]-1:0);valid[index]=true;history=((history<<1)|taken)&15;}
   if(bt && !(w&1) && (bytes==2 || bytes==4)){
    unsigned op=insn&127,f=(insn>>12)&7,kind=0;uint64_t target=next;
    if(op==0x63 && (f<=1 || f>=4)){kind=1;int off=((insn>>31)<<12)|(((insn>>7)&1)<<11)|(((insn>>25)&63)<<5)|(((insn>>8)&15)<<1);if(off&4096)off-=8192;target=w+off;}
    if(op==0x6f){kind=2;int off=((insn>>31)<<20)|(((insn>>12)&255)<<12)|(((insn>>20)&1)<<11)|(((insn>>21)&1023)<<1);if(off&1048576)off-=2097152;target=w+off;}
    if(op==0x67 && f==0){unsigned rd=(insn>>7)&31,rs=(insn>>15)&31;kind=rd==0 && (rs==1||rs==5) && insn>>20==0?3:4;}
    if(kind)table[(w>>1)&31]={true,w,target,kind,bytes,kind==1&&bool(insn>>31)};
   }
  }
  d.clk=1;d.eval();check();++steps;
 };
 step(0,0,0,0,4,0,0,0,0,0,1,0,0);
 for(unsigned slot=0;slot<32;++slot)for(uint32_t insn:{0xfe001ce3u,0x00000463u,0x008000efu,0x00008067u,0x000300e7u}){
  uint64_t pc=0x800+slot*2;step(pc,pc,insn,0x900,slot&1?2:4,1,1,1,slot,0,0,0,0);
  step(pc,0,0,0,4,0,0,0,0,0,0,1,0x920);step(pc,0,0,0,4,0,0,0,0,0,0,1,0x1000);
 }
 for(unsigned i=0;i<30000;++i){uint64_t pc=random(),w=random(),f=random();uint32_t insn=random();
  switch(i%5){case 0:insn=(insn&~127u)|0x63;break;case 1:insn=(insn&~127u)|0x6f;break;case 2:insn=0x00008067;break;case 3:insn=0x000300e7;break;default:break;}
  if(i%3==0)pc=w;step(pc,w,insn,random(),f&7,f&8,f&16,f&32,(f>>8)&31,(f&511)==0,(f&2047)==1,f&64,random());
 }
 std::cout<<"PREFETCH PREDICTOR MODEL PASS: "<<steps<<" steps, enabled="<<EXPECT_ENABLE<<"\n";
}
