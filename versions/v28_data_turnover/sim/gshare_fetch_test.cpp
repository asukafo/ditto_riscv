#define main legacy_fetch_test_main
#include "fetch_test.cpp"
#undef main
int main(){try{unsigned checks=0;
    for(auto cfg:std::array<std::array<unsigned,2>,3>{{{{1,0}},{{5,3}},{{20,7}}}}){
        Memory m(cfg[0],cfg[1]);m.put32(0,0x00000463); // BEQ x0,x0,+8: cold predicts +4.
        m.top.ready=0;
        for(unsigned i=0;i<1000 && !m.top.valid;++i)m.step();
        check(m.top.valid && m.top.pc==0 && m.top.predicted_next==4 && m.top.predicted_index==0,"cold packet metadata wrong");++checks;
        unsigned saved=m.top.predicted_index;
        // Train other committed branches while this F packet is backpressured.
        for(unsigned i=0;i<8;++i){m.top.bht_train=1;m.top.bht_train_taken=1;m.top.bht_train_index=31;m.top.bht_train_pc=62;m.step();
            check(m.top.valid && m.top.predicted_index==saved && m.top.predicted_next==4,"held packet recomputed its index/prediction");++checks;}
        check(m.top.global_history==15,"committed history shift failed");++checks;
        // Train the original lookup index, not PC XOR the now-current history.
        m.top.bht_train_index=saved;m.top.bht_train_pc=0;m.step();m.top.bht_train=0;
        // Clear has priority over a coincident write; redirect cancels the packet.
        m.top.bht_clear=1;m.top.bht_train=1;m.top.bht_train_index=15;m.redirect(0);m.top.bht_clear=0;m.top.bht_train=0;
        check(m.top.global_history==0,"clear did not win over training");++checks;
        m.top.ready=0;for(unsigned i=0;i<1000 && !m.top.valid;++i)m.step();
        check(m.top.valid && !m.top.predicted_dynamic && m.top.predicted_index==0 && m.top.predicted_next==4,"clear retained stale history/table entry");++checks;
        // A taken training leaves history=1: halfword PC=2 must select slot 0.
        m.top.bht_train=1;m.top.bht_train_taken=1;m.top.bht_train_index=0;m.top.bht_train_pc=0;m.step();m.top.bht_train=0;
        m.redirect(2);m.top.ready=0;for(unsigned i=0;i<1000 && !m.top.valid;++i)m.step();
        check(m.top.valid && m.top.predicted_index==0,"halfword PC XOR history index wrong");++checks;
    }
    std::cout<<"GSHARE FETCH PASS: "<<checks<<" checks with memory/output backpressure\n";return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
