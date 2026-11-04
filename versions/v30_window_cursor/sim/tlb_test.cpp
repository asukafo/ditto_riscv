#include "Vrv64_tlb.h"
#include "verilated.h"
#include <array>
#include <cstdint>
#include <iostream>
#include <stdexcept>
static void check(bool x,const char* why){if(!x)throw std::runtime_error(why);}
struct Entry{bool valid=false;uint64_t vpn=0,context=0,ppn=0;unsigned flags=0;};
int main(){try{VerilatedContext ctx;Vrv64_tlb t{&ctx};std::array<Entry,8> model{};unsigned next=0,checks=0;
    t.clk=0;t.reset=1;t.invalidate=0;t.lookup_valid=0;t.fill_valid=0;t.lookup_vaddr=0;t.lookup_context=0;t.fill_vaddr=0;t.fill_context=0;t.fill_ppn=0;t.fill_flags=0;t.eval();t.clk=1;t.eval();t.reset=0;
    uint64_t rng=0x12345;
    auto rand=[&](){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;return rng;};
    for(unsigned step=0;step<12000;++step){
        uint64_t vpn=rand()%16,context=(uint64_t(8)<<60)|(rand()%3<<44)|(rand()%2+6);
        t.clk=0;t.invalidate=step%97==0;t.lookup_valid=1;t.lookup_vaddr=(vpn<<12)|(rand()&4095);t.lookup_context=context;
        t.fill_valid=step%3!=0;t.fill_vaddr=(rand()%16)<<12;t.fill_context=(uint64_t(8)<<60)|(rand()%3<<44)|(rand()%2+6);t.fill_ppn=rand()&((uint64_t(1)<<44)-1);t.fill_flags=rand()&255;t.eval();
        const Entry* hit=nullptr;for(auto& e:model)if(e.valid&&e.vpn==vpn&&e.context==context)hit=&e;
        if(t.invalidate)hit=nullptr;
        check(bool(t.hit)==bool(hit)&&bool(t.hit_event)==bool(hit)&&bool(t.miss_event)==!bool(hit),"lookup/context mismatch");
        if(hit)check(t.ppn==hit->ppn&&t.flags==hit->flags,"cached translation data corrupted");
        check(bool(t.fill_event)==bool(t.fill_valid&&!t.invalidate),"fill event wrong");
        if(t.invalidate){for(auto& e:model)e.valid=false;next=0;}
        else if(t.fill_valid){
            unsigned dest=next;bool duplicate=false;
            for(unsigned i=0;i<8;++i)if(model[i].valid&&model[i].vpn==(t.fill_vaddr>>12)&&model[i].context==t.fill_context){dest=i;duplicate=true;break;}
            if(!duplicate)for(unsigned i=0;i<8;++i)if(!model[i].valid){dest=i;break;}
            model[dest]={true,t.fill_vaddr>>12,t.fill_context,t.fill_ppn,unsigned(t.fill_flags)};if(!duplicate)next=(dest+1)%8;
        }
        t.clk=1;t.eval();++checks;
    }
    std::cout<<"TLB UNIT PASS: "<<checks<<" model steps, contexts/replacement/duplicate fill/invalidation\n";return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
