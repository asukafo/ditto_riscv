#include "Vrv64_bht.h"
#include "verilated.h"
#include <array>
#include <cassert>
#include <cstdint>
#include <iostream>
#ifndef EXPECT_ENABLE
#define EXPECT_ENABLE 1
#endif
int main() {
    Vrv64_bht d; std::array<unsigned,32> c{}; std::array<bool,32> v{};
    uint64_t rng=0x1974abcd; unsigned steps=0;
    auto random=[&](){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;return rng;};
    auto step=[&](uint64_t r,uint64_t w,bool t,bool taken,bool clear,bool reset){
        d.clk=0;d.lookup_pc=r;d.train_pc=w;d.train=t;d.train_taken=taken;d.clear=clear;d.reset=reset;d.eval();
        unsigned ri=(r>>1)&31,wi=(w>>1)&31;
        assert(bool(d.hit)==bool(EXPECT_ENABLE && v[ri]));
        assert(bool(d.taken)==bool(EXPECT_ENABLE && v[ri] && c[ri]>=2));
        if(reset || clear || !EXPECT_ENABLE){v.fill(false);c.fill(1);}
        else if(t){c[wi]=!v[wi] ? (taken?2:1) : taken ? (c[wi]<3?c[wi]+1:3) : (c[wi]?c[wi]-1:0);v[wi]=true;}
        d.clk=1;d.eval();
        assert(bool(d.hit)==bool(EXPECT_ENABLE && v[ri]));
        assert(bool(d.taken)==bool(EXPECT_ENABLE && v[ri] && c[ri]>=2));++steps;
    };
    step(0,0,0,0,0,1);
    // Saturation, hysteresis, halfword indexing, high-PC alias, clear wins over training.
    for(unsigned i=0;i<32;++i){
        for(unsigned j=0;j<5;++j)step(i*2,i*2,1,1,0,0);
        for(unsigned j=0;j<5;++j)step(i*2,i*2,1,0,0,0);
        step(i*2+0x8000000000000040ULL,i*2,1,1,0,0);
    }
    step(0,0,1,1,1,0);
    for(unsigned i=0;i<20000;++i){uint64_t r=random(),w=random();auto f=random();step(r,w,f&1,f&2,(f&255)==0,(f&1023)==3);}
    std::cout<<"BHT MODEL PASS: "<<steps<<" steps, enabled="<<EXPECT_ENABLE<<"\n";
}
