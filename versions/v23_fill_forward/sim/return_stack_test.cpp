#include "Vrv64_return_stack.h"
#include "verilated.h"
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <vector>
#ifndef EXPECT_ENABLE
#define EXPECT_ENABLE 1
#endif
static void check(bool x,const char* why){if(!x)throw std::runtime_error(why);}
int main(){try{VerilatedContext ctx;Vrv64_return_stack t{&ctx};std::vector<uint64_t> model;unsigned checks=0;uint64_t serial=0;
    auto step=[&](uint32_t ins,uint64_t pc,unsigned bytes,bool retire=true,bool clear=false,bool reset=false){
        t.clk=0;t.insn=ins;t.pc=pc;t.bytes=bytes;t.retire=retire;t.clear=clear;t.reset=reset;t.eval();
        unsigned rd=(ins>>7)&31,rs=(ins>>15)&31;bool rdlink=rd==1||rd==5,rslink=rs==1||rs==5;
        bool jal=(ins&127)==0x6f,jalr=(ins&0x707f)==0x67;
        bool push=(jal||jalr)&&rdlink,pop=jalr&&rslink&&(!rdlink||rd!=rs);
        bool update=EXPECT_ENABLE && retire && !clear && !reset;
        check(bool(t.push_event)==(update&&push)&&bool(t.pop_event)==(update&&pop),"wrong call/return hint action");
        check(bool(t.overflow_event)==(update&&push&&!pop&&model.size()==8)&&bool(t.underflow_event)==(update&&pop&&model.empty()),"overflow/underflow event wrong");
        if(reset||clear||!EXPECT_ENABLE)model.clear();else if(update){
            if(pop&&!model.empty())model.erase(model.begin());
            if(push){model.insert(model.begin(),pc+bytes);if(model.size()>8)model.pop_back();}
        }
        t.clk=1;t.eval();
        check(t.occupancy==model.size()&&bool(t.valid)==!model.empty(),"stack occupancy mismatch");
        check(t.target==(model.empty()?0:model.front()),"stack top mismatch");++checks;
    };
    step(0,0,4,false,false,true);
    for(unsigned rd=0;rd<32;++rd)for(unsigned rs=0;rs<32;++rs)for(unsigned op:{0x6fu,0x67u,0x23u}){
        uint32_t ins=(rd<<7)|(rs<<15)|op;
        for(unsigned bytes:{2u,4u}){step(ins,0x1000+serial++*4,bytes);step(ins,0x2000,bytes,false);}
        if(serial%29==0)step(0,0,4,false,true);
    }
    step(0,0,4,false,true);
    for(unsigned i=0;i<12;++i)step(0xef,0x100+i*4,i%2?2:4);
    for(unsigned i=0;i<12;++i)step(0x8067,0,4);
    step(0xef,0xfffffffffffffffcull,4);
    step(0x8067,0,4);
    // Same link register pushes; different link registers pop then push.
    step(0x000080e7,0x200,4);step(0x000082e7,0x300,2);step(0x00028067,0,4);
    step(0xef,0x400,4,true,true);step(0xef,0x500,4,false);
    // Reserved JALR funct3 never changes history.
    for(unsigned f=1;f<8;++f)step(0x000080e7|(f<<12),0x600,4);
    std::cout<<"RETURN STACK UNIT PASS: "<<checks<<" steps, enabled="<<EXPECT_ENABLE<<'\n';return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
