#include "Vrv64_bht.h"
#include "verilated.h"
#include <array>
#include <cassert>
#include <cstdint>
#include <iostream>
#ifndef EXPECT_ENABLE
#define EXPECT_ENABLE 1
#endif
#ifndef EXPECT_GSHARE
#define EXPECT_GSHARE 1
#endif
int main() {
    Vrv64_bht d; std::array<unsigned,32> c{}; std::array<bool,32> v{};
    unsigned history=0,steps=0;uint64_t rng=0x1974abcd;
    auto random=[&](){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;return rng;};
    auto step=[&](uint64_t r,uint64_t w,unsigned saved,bool train,bool taken,bool clear,bool reset){
        d.clk=0;d.lookup_pc=r;d.train_pc=w;d.train_index=saved;d.train=train;d.train_taken=taken;d.clear=clear;d.reset=reset;d.eval();
        auto verify=[&](){unsigned ri=((r>>1)&31)^(EXPECT_GSHARE?history:0);
            assert(unsigned(d.global_history)==history);assert(unsigned(d.lookup_index)==ri);
            assert(bool(d.hit)==bool(EXPECT_ENABLE && v[ri]));
            assert(bool(d.taken)==bool(EXPECT_ENABLE && v[ri] && c[ri]>=2));};
        verify();
        if(reset || clear || !EXPECT_ENABLE){v.fill(false);c.fill(1);history=0;}
        else if(train){unsigned wi=EXPECT_GSHARE?saved:((w>>1)&31);
            c[wi]=!v[wi] ? (taken?2:1) : taken ? (c[wi]<3?c[wi]+1:3) : (c[wi]?c[wi]-1:0);v[wi]=true;
            if(EXPECT_GSHARE)history=((history<<1)|taken)&15;
        }
        d.clk=1;d.eval();verify();++steps;
    };
    step(0,0,0,0,0,0,1);
    // All 32 saved indices, saturation and hysteresis independent of current GHR.
    for(unsigned i=0;i<32;++i){
        for(unsigned j=0;j<5;++j)step(i*2,i*2,i,1,1,0,0);
        for(unsigned j=0;j<5;++j)step(i*2,i*2,i,1,0,0,0);
        step(i*2+0x8000000000000040ULL,i*2,i,1,1,0,0);
    }
    step(0,0,0,1,1,1,0);
    // Save a lookup, advance history, then update the original saved slot.
    step(0x12,0,0,0,0,0,0);unsigned saved=d.lookup_index;
    for(unsigned i=0;i<6;++i)step(0x20,0x20,16,1,1,0,0);
    step(0x12,0x12,saved,1,0,0,0);
    for(unsigned i=0;i<30000;++i){uint64_t r=random(),w=random();unsigned saved_index=random()&31;auto f=random();
        step(r,w,saved_index,f&1,f&2,(f&255)==0,(f&1023)==3);}
    std::cout<<"HISTORY MODEL PASS: "<<steps<<" steps, enabled="<<EXPECT_ENABLE<<", gshare="<<EXPECT_GSHARE<<"\n";
}
