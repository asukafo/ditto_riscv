#include "Vrv64_btb.h"
#include "verilated.h"
#include <array>
#include <cassert>
#include <cstdint>
#include <iostream>
#ifndef EXPECT_ENABLE
#define EXPECT_ENABLE 1
#endif
struct Entry {bool valid=false;uint64_t pc=0,target=0;unsigned kind=0,bytes=0;bool backward=false;};
int main(){Vrv64_btb d;std::array<Entry,32> entries{};unsigned steps=0;uint64_t rng=0x11223344;
 auto random=[&](){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;return rng;};
 auto step=[&](uint64_t pc,uint64_t w,uint32_t insn,uint64_t next,unsigned bytes,bool train,bool clear,bool reset){
  d.clk=0;d.lookup_pc=pc;d.train_pc=w;d.train_insn=insn;d.train_next=next;d.train_bytes=bytes;d.train=train;d.clear=clear;d.reset=reset;d.eval();
  auto check=[&](){auto e=entries[(pc>>1)&31];bool hit=EXPECT_ENABLE && !(pc&1) && e.valid && e.pc==pc;
   assert(bool(d.hit)==hit);assert(d.kind==(hit?e.kind:0));assert(d.bytes==(hit?e.bytes:0));assert(d.target==(hit?e.target:0));assert(bool(d.backward)==(hit&&e.backward));};check();
  if(reset || clear || !EXPECT_ENABLE)entries={};
  else if(train && !(w&1) && (bytes==2 || bytes==4)){
   unsigned op=insn&127,f=(insn>>12)&7,kind=0;uint64_t target=next;
   if(op==0x63 && (f<=1 || f>=4)){kind=1;int off=((insn>>31)<<12)|(((insn>>7)&1)<<11)|(((insn>>25)&63)<<5)|(((insn>>8)&15)<<1);if(off&4096)off-=8192;target=w+off;}
   if(op==0x6f){kind=2;int off=((insn>>31)<<20)|(((insn>>12)&255)<<12)|(((insn>>20)&1)<<11)|(((insn>>21)&1023)<<1);if(off&1048576)off-=2097152;target=w+off;}
   if(op==0x67 && f==0){unsigned rd=(insn>>7)&31,rs=(insn>>15)&31;kind=rd==0 && (rs==1 || rs==5) && (insn>>20)==0?3:4;}
   if(kind)entries[(w>>1)&31]={true,w,target,kind,bytes,kind==1 && bool(insn>>31)};
  }
  d.clk=1;d.eval();check();++steps;
 };
 step(0,0,0,0,4,0,0,1);
 for(unsigned slot=0;slot<32;++slot){uint64_t pc=slot*2;
  for(uint32_t insn:{0xfe001ce3u,0x00000463u,0x008000efu,0x00008067u,0x00028067u,0x000300e7u}){
   step(pc,pc,insn,0x1234,slot&1?2:4,1,0,0);step(pc+64,pc+64,insn,0x4320,4,1,0,0);step(pc,0,0,0,4,0,0,0);
  }
 }
 step(0,0,0x0080006f,0,4,1,1,0);
 for(unsigned i=0;i<25000;++i){uint64_t pc=random(),w=random(),f=random();uint32_t insn=random();
  if(i%3==0)insn=(insn&~127u)|0x63;if(i%3==1)insn=(insn&~127u)|0x6f;if(i%7==0)pc=w;
  step(pc,w,insn,random(),f&7,f&8,(f&511)==0,(f&2047)==1);
 }
 std::cout<<"BTB MODEL PASS: "<<steps<<" steps, enabled="<<EXPECT_ENABLE<<"\n";
}
