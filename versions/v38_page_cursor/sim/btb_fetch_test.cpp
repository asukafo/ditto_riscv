#define main legacy_fetch_test_main
#include "fetch_test.cpp"
#undef main
int main(){try{unsigned checks=0;
 for(auto cfg:std::array<std::array<unsigned,2>,3>{{{{1,0}},{{5,3}},{{20,7}}}}){
  auto train=[](Memory& m,unsigned insn,unsigned bytes,uint64_t next){m.top.btb_train=1;m.top.btb_train_pc=0;m.top.btb_train_insn=insn;m.top.btb_train_bytes=bytes;m.top.btb_train_next=next;m.top.req_ready=0;m.top.redirect=1;m.step();m.top.redirect=0;m.top.btb_train=0;};
  // The target exists before any instruction response. A held packet keeps it.
  Memory m(cfg[0],cfg[1]);m.put32(0,0x000300e7);m.put16(0x80,1);train(m,0x000300e7,4,0x80);
  m.top.ready=0;for(unsigned i=0;i<1000 && !m.top.valid;++i)m.step();
  check(m.top.valid && m.top.predicted_btb && m.top.predicted_next==0x80,"indirect BTB prediction not used");++checks;
  for(unsigned i=0;i<8;++i)m.step();++checks;
  // A changed direct target is rejected before issuing the old target fetch.
  Memory stale(cfg[0],cfg[1]);stale.put32(0,0x0100006f);train(stale,0x0080006f,4,0);
  stale.collect(2);check(stale.instructions[0].prediction==16 && !stale.instructions[0].btb && stale.instructions[1].pc==16,"stale direct target escaped validation");++checks;
  // A stale control-flow entry over ordinary code cannot redirect the stream.
  Memory ordinary(cfg[0],cfg[1]);ordinary.put32(0,0x00150513);train(ordinary,0x0080006f,4,0);
  ordinary.collect(2);check(ordinary.instructions[0].prediction==4 && !ordinary.instructions[0].btb && ordinary.instructions[1].pc==4,"BTB false control identification");++checks;
  Memory length(cfg[0],cfg[1]);length.put16(0,0xa011);train(length,0x0080006f,4,0);
  length.collect(2);check(length.instructions[0].bytes==2 && !length.instructions[0].btb && length.instructions[1].pc==4,"stale instruction length accepted");++checks;
  // A request-time direction can be stale by response time. Refresh both direction
  // and its training index before producing the packet; no successor was issued.
  Memory direction(20,7);direction.put32(0,0x00000463);train(direction,0x00000463,4,0);
  direction.top.ready=0;for(unsigned i=0;i<1000 && !direction.pending;++i)direction.step();
  for(unsigned i=0;i<5;++i){direction.top.bht_train=1;direction.top.bht_train_index=15;direction.top.bht_train_pc=0;direction.top.bht_train_taken=1;direction.step();}
  direction.top.bht_train=0;for(unsigned i=0;i<1000 && !direction.top.valid;++i)direction.step();
  check(direction.top.valid && direction.top.predicted_btb && direction.top.predicted_dynamic && direction.top.predicted_index==15 && direction.top.predicted_next==8,"late direction/index refresh failed");++checks;
  // Clear with training wins; the prediction must revert to sequential JALR.
  m.top.bht_clear=1;m.top.btb_train=1;m.redirect(0);m.top.bht_clear=0;m.top.btb_train=0;m.top.ready=0;
  for(unsigned i=0;i<1000 && !m.top.valid;++i)m.step();
  check(!m.top.predicted_btb && m.top.predicted_next==4,"BTB entry survived clear");++checks;
 }
 std::cout<<"BTB FETCH PASS: "<<checks<<" checks with memory/output backpressure\n";return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
