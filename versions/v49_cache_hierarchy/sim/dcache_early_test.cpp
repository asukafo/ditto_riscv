#define main legacy_data_cache_test_main
#include "dcache_test.cpp"
#undef main

static void drain(Memory& m) {
    m.top.u_valid=0;m.top.u_rsp_ready=1;
    for (unsigned i=0;i<1000;++i) {
        m.step();
        if (m.top.u_ready) return;
    }
    throw std::runtime_error("background refill did not drain");
}
int main() {
    try {
        unsigned checks=0;
#ifdef EXPECT_DATA_UNDER_REFILL
        // Cover a resident line, the buffered critical half and the returning tail.
        for (uint64_t next : {0x20ull, 0x40ull, 0x48ull}) {
            Memory overlap(20,0);
            check(!overlap.access(0x20).error,"resident line setup");
            drain(overlap);
            check(!overlap.access(0x40).error,"critical half setup");
            overlap.top.u_addr=next;
            overlap.top.u_valid=1;
            overlap.top.u_rsp_ready=0;
            bool accepted=false;
            for (unsigned i=0;i<100 && !accepted;++i) {
                bool tail_returning=overlap.pending && overlap.remaining==0;
                auto edge=overlap.step();
                accepted=edge.accepted;
                if (next==0x48 && accepted) check(tail_returning,"tail read accepted before data");
                if (next!=0x48 && i==0) check(accepted,"ready hit blocked behind tail");
            }
            check(accepted,"background load never accepted");
            overlap.top.u_valid=0;
            for (unsigned i=0;i<30;++i) overlap.step();
            overlap.top.u_rsp_ready=1;
            auto edge=overlap.step();
            check(edge.returned && !edge.result.error && edge.result.data==overlap.read(next,2),
                  "background response lost, reordered or corrupted");
            drain(overlap);
            check(overlap.requests.size()==4,"background hit sent another physical request");
            checks+=3;
        }
        Memory failed_tail(20,0);
        failed_tail.fail_address=0x48;
        check(!failed_tail.access(0x40).error,"critical load before failed tail");
        for (unsigned i=0;i<100 && (!failed_tail.pending || failed_tail.remaining>0);++i)
            failed_tail.step();
        check(failed_tail.pending && failed_tail.remaining==0,"failed tail never returned");
        failed_tail.top.u_addr=0x48;
        failed_tail.top.u_valid=1;
        check(!failed_tail.step().accepted,"failed tail was offered as a successful load");
        failed_tail.top.u_valid=0;
        drain(failed_tail);
        check(failed_tail.access(0x48).error,"demand retry did not receive the real fault");
        checks+=2;
#endif
#ifdef EXPECT_REFILL_FORWARD
        Memory fast(5,0);
        fast.top.u_valid=1;
        fast.top.u_addr=0x2c;
        fast.top.u_size=2;
        auto launch=fast.step();
        check(launch.accepted && fast.requests.size()==1 && fast.requests[0].address==0x28,
              "demand and first refill beat did not handshake together");
        fast.top.u_valid=0;
        while(fast.remaining>0) fast.step();
        auto critical=fast.step();
        check(critical.returned && !critical.result.error && critical.result.data==fast.read(0x2c,2),
              "critical return was not forwarded on the downstream response edge");
        drain(fast);
        check(fast.requests.size()==2,"forwarding did not drain the remainder");
        checks+=3;
#endif
        for (auto config:std::array<std::array<int,2>,3>{{{{1,0}},{{5,3}},{{20,7}}}}) {
            for (uint64_t address:{0x20ull,0x2cull}) {
                Memory m(config[0],config[1]);
                Result r=m.access(address);
                check(!r.error && r.data==m.read(address,2),"wrong critical word");++checks;
                check(m.requests.front().address==(address&~7ull),"critical beat was not first");++checks;
                // For long latency the response must precede the remaining response.
                if (config[0]>=5) {check(m.pending || m.requests.size()==1,"did not restart before refill finished");++checks;}
                drain(m);
                check(m.requests.size()==2 && m.requests[1].address==((address&~15ull)+(address&8 ? 0:8)),"wrong remainder beat");++checks;
                for (unsigned offset=0;offset<16;offset+=2) {
                    auto hit=m.access((address&~15ull)+offset,1);
                    check(!hit.error && hit.data==m.read((address&~15ull)+offset,1),"reordered line assembled incorrectly");++checks;
                }
                check(m.requests.size()==2,"completed line did not hit");++checks;
            }
            // An error in the requested beat faults; the speculative remainder does not.
            for (bool critical_failure:{false,true}) {
                Memory m(config[0],config[1]);m.fail_address=critical_failure ? 0x48:0x40;
                Result r=m.access(0x4c);
                check(r.error==critical_failure,"wrong error ownership");++checks;
                if (!r.error) check(r.data==m.read(0x4c,2),"bad early response");
                drain(m);size_t before=m.requests.size();m.fail_address=~uint64_t(0);
                r=m.access(0x4c);drain(m);
                check(!r.error && m.requests.size()==before+2,"failed refill allocated valid line");++checks;
            }
            // A request straddling the 8-byte boundary must wait for both beats.
            Memory cross(config[0],config[1]);auto r=cross.access(0x56,2);drain(cross);
            check(!r.error && r.data==cross.read(0x56,2) && cross.requests[0].address==0x50,"cross-beat fallback failed");++checks;
            // Invalidate after early response but while remainder is in flight.
            Memory poison(20,7);r=poison.access(0x60);poison.invalidate();drain(poison);
            size_t before=poison.requests.size();r=poison.access(0x60);drain(poison);
            check(!r.error && poison.requests.size()==before+2,"invalidated remainder revalidated line");++checks;
            // A peer writes the first beat after it was returned. The tail
            // may finish, but must not revalidate a mixed-version line.
            Memory peer(20,7);r=peer.access(0x60);
            check(!r.error && peer.requests.size()==1,"expected a pending tail");
            peer.ram[0x60]=0x5a;
            peer.top.snoop_line=0x60>>4;peer.top.snoop_write=1;
            peer.step();peer.top.snoop_write=0;
            drain(peer);
            before=peer.requests.size();r=peer.access(0x60);drain(peer);
            check(!r.error && r.data==peer.read(0x60,2) && peer.requests.size()==before+2,
                  "snooped tail installed stale bytes");++checks;
            // Hold the first response until well after the background refill finishes.
            Memory blocked(config[0],config[1]);blocked.top.u_addr=0x78;blocked.top.u_valid=1;blocked.top.u_rsp_ready=0;
            bool accepted=false;
            for (unsigned i=0;i<1000 && !accepted;++i) accepted=blocked.step().accepted;
            check(accepted,"held-response request not accepted");blocked.top.u_valid=0;
            for (unsigned i=0;i<200;++i) blocked.step();
            check(blocked.top.u_rsp_valid && !blocked.top.u_ready,"lost held response or accepted new request");++checks;
            blocked.top.u_rsp_ready=1;auto edge=blocked.step();
            check(edge.returned && edge.result.data==blocked.read(0x78,2) && !edge.result.error,"held response corrupted");++checks;
            drain(blocked);check(blocked.requests.size()==2,"backpressure repeated refill");++checks;
        }
        // A following store must wait for the background fill, then update the completed line.
        for(bool atomic:{false,true}) {
            Memory m(20,7);auto first=m.access(0x90);
            check(!first.error,"initial early load failed");
            m.top.u_addr=0x90;m.top.u_data=0x12345678;m.top.u_size=2;
            m.top.u_write=1;m.top.u_atomic=atomic;m.top.u_amo=0;m.top.u_valid=1;m.top.u_rsp_ready=1;
            bool accepted=false;
            for(unsigned i=0;i<1000 && !accepted;++i) accepted=m.step().accepted;
            check(accepted && m.requests.size()==3 && m.requests[1].address==0x98 && m.requests[2].address==0x90,
                  "store/atomic overtook background refill");++checks;
            m.top.u_valid=0;
            bool returned=false;for(unsigned i=0;i<1000 && !returned;++i) returned=m.step().returned;
            check(returned,"following store/atomic response lost");++checks;
            size_t n=m.requests.size();auto next=m.access(0x90);drain(m);
            check(!next.error && next.data==0x12345678 && m.requests.size()==n+(atomic ? 2:0),
                  "following store/atomic left stale line");++checks;
        }
        // The held early response must remain successful if the later speculative read fails.
        Memory held(5,3);held.fail_address=0xb8;
        held.top.u_addr=0xb0;held.top.u_valid=1;held.top.u_rsp_ready=0;
        bool accepted=false;for(unsigned i=0;i<1000 && !accepted;++i) accepted=held.step().accepted;
        check(accepted,"held error case not accepted");held.top.u_valid=0;
        for(unsigned i=0;i<200;++i) held.step();
        check(held.top.u_rsp_valid && !held.top.u_rsp_error && held.top.u_rsp_data==held.read(0xb0,2),
              "remainder error corrupted held early response");++checks;
        held.top.u_rsp_ready=1;held.step();drain(held);size_t n=held.requests.size();held.fail_address=~uint64_t(0);
        held.access(0xb0);drain(held);check(held.requests.size()==n+2,"error remainder allocated line");++checks;
        std::cout<<"DCACHE EARLY UNIT PASS: "<<checks<<" checks across 3 latency/backpressure configurations\n";
        return 0;
    } catch (const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;}
}
