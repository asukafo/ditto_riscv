#include "Vrv64_physical_arbiter.h"
#include "verilated.h"
#include <array>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <vector>
static void check(bool x,const char* why){if(!x)throw std::runtime_error(why);}
int main(){try{
    unsigned total=0;
    for(auto cfg:std::array<std::array<unsigned,2>,3>{{{{1,0}},{{5,3}},{{20,7}}}}){
        VerilatedContext ctx;Vrv64_physical_arbiter t{&ctx};
        t.clk=0;t.reset=1;t.c_valid=0;t.c_rsp_ready=0;t.u_ready=0;t.u_rsp_valid=0;t.eval();t.clk=1;t.eval();t.reset=0;
        std::array<unsigned,4> done{};std::array<bool,4> active{};
        std::vector<unsigned> accepted;unsigned issued=0,returned=0,remaining=0,owner=0;
        bool pending=false,blocked=false;uint64_t held_addr=0,held_data=0;unsigned held_size=0,held_amo=0;bool held_write=false,held_atomic=false;
        for(unsigned tick=0;tick<30000 && returned<48;++tick){
            t.clk=0;t.c_valid=0;t.c_rsp_ready=0;t.c_size=0;t.c_write=0;t.c_atomic=0;t.c_amo=0;
            for(unsigned i=0;i<4;++i){
                if(!active[i] && done[i]<12)t.c_valid|=1u<<i;
                if(tick%(i+3)!=0)t.c_rsp_ready|=1u<<i;
                uint64_t addr=0x1000+0x100*i+8*done[i],data=0xabc000+i*16+done[i];
                t.c_addr[i*2]=uint32_t(addr);t.c_addr[i*2+1]=uint32_t(addr>>32);
                t.c_data[i*2]=uint32_t(data);t.c_data[i*2+1]=uint32_t(data>>32);
                t.c_size|=(i%4)<<(i*2);t.c_write|=(i&1)<<i;t.c_atomic|=(i==1)<<i;t.c_amo|=(i+2)<<(i*5);
            }
            t.u_ready=!pending && tick%(cfg[1]+1)==0;t.u_rsp_valid=pending && remaining==0;t.eval();
            if(blocked)check(t.u_valid && t.u_addr==held_addr && t.u_data==held_data && t.u_size==held_size && t.u_amo==held_amo && bool(t.u_write)==held_write && bool(t.u_atomic)==held_atomic,"physical request changed under backpressure");
            blocked=t.u_valid && !t.u_ready;held_addr=t.u_addr;held_data=t.u_data;held_size=t.u_size;held_amo=t.u_amo;held_write=t.u_write;held_atomic=t.u_atomic;
            unsigned accepts=t.c_valid&t.c_ready;
            check((accepts&(accepts-1))==0,"accepted two clients");
            for(unsigned i=0;i<4;++i)if(accepts&(1u<<i)){check(!active[i],"duplicate client acceptance");active[i]=true;accepted.push_back(i);}
            bool issue=t.u_valid&&t.u_ready,consume=t.u_rsp_valid&&t.u_rsp_ready;
            if(issue){
                check(!pending && issued<accepted.size(),"downstream ownership missing");owner=accepted[issued];
                check(t.u_addr==0x1000+0x100*owner+8*done[owner] && t.u_data==0xabc000+owner*16+done[owner] && t.u_size==owner%4 && t.u_amo==owner+2 && bool(t.u_write)==bool(owner&1) && bool(t.u_atomic)==(owner==1),"request metadata or owner corrupted");++issued;
            }
            if(t.c_rsp_valid)check(pending && t.c_rsp_valid==(1u<<owner),"response sent to wrong client");
            if(consume){check(t.c_rsp_ready&(1u<<owner),"response consumed against client backpressure");active[owner]=false;++done[owner];++returned;}
            t.clk=1;t.eval();
            if(consume)pending=false;
            if(issue){pending=true;remaining=cfg[0]-1;}else if(pending && remaining)--remaining;
        }
        check(returned==48 && issued==48,"arbiter progress timeout");
        for(unsigned i=0;i<accepted.size();++i)check(accepted[i]==i%4,"round-robin fairness broken");
        total+=returned;
    }
    std::cout<<"PHYSICAL ARBITER PASS: "<<total<<" transactions, metadata/ownership/backpressure/round-robin checked\n";return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
