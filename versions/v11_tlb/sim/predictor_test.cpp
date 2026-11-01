#include "Vrv64_static_predictor.h"
#include "verilated.h"
#include <array>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#ifndef EXPECT_C
#define EXPECT_C 1
#endif
static uint32_t branch(int32_t offset,unsigned funct){uint32_t x=uint32_t(offset)&8191;return ((x>>12)<<31)|(((x>>5)&63)<<25)|(((x>>1)&15)<<8)|(((x>>11)&1)<<7)|(funct<<12)|0x63;}
static uint32_t jump(int32_t offset){uint32_t x=uint32_t(offset)&0x1fffff;return ((x>>20)<<31)|(((x>>1)&1023)<<21)|(((x>>11)&1)<<20)|(((x>>12)&255)<<12)|0xef;}
int main(){try{VerilatedContext c;Vrv64_static_predictor t{&c};unsigned checks=0;
    auto verify=[&](uint64_t pc,uint32_t ins,unsigned bytes,bool legal,uint64_t expected){t.pc=pc;t.insn=ins;t.bytes=bytes;t.legal=legal;t.eval();if(t.predicted_next!=expected)throw std::runtime_error("static prediction mismatch");++checks;};
    for(uint64_t pc:{0ull,0x100ull,0xfffffffffffffffcull})for(unsigned bytes:{2u,4u}){
        if(!EXPECT_C && bytes==2)continue;
        for(int offset=-4096;offset<=4094;offset+=2)for(unsigned f=0;f<8;++f){
            uint64_t target=pc+uint64_t(int64_t(offset));bool aligned=EXPECT_C || (target&3)==0;
            bool take=offset<0 && (f<=1||f>=4) && aligned;
            verify(pc,branch(offset,f),bytes,true,take?target:pc+bytes);
            verify(pc,branch(offset,f),bytes,false,pc+bytes);
        }
        for(int offset:{-1048576,-4096,-2,0,2,4,4094,1048574}){
            uint64_t target=pc+uint64_t(int64_t(offset));bool aligned=EXPECT_C || (target&3)==0;
            verify(pc,jump(offset),bytes,true,aligned?target:pc+bytes);verify(pc,jump(offset),bytes,false,pc+bytes);
        }
        for(uint32_t ins:{0x00008067u,0x00150513u,0xffffffffu})verify(pc,ins,bytes,true,pc+bytes);
    }
    std::cout<<"STATIC PREDICTOR UNIT PASS: "<<checks<<" vectors, C="<<EXPECT_C<<'\n';return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
