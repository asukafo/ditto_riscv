// Independent read copy of the committed predictors. Prefetch never trains it.
// Read words stay within one page and four-byte alignment; F owns actual decoding.
module rv64_prefetch_predictor #(parameter ENABLED=1,BHT_ENABLE=1,GSHARE_ENABLE=1)(
 input wire clk,reset,clear,input wire [63:0] pc,
 input wire btb_train,bht_train,train_taken,input wire [63:0] train_pc,train_next,
 input wire [31:0] train_insn,input wire [2:0] train_bytes,input wire [4:0] train_index,
 input wire ras_valid,input wire [63:0] ras_target,
 output wire hint,page_block,output wire [63:0] next_pc,target,
 output wire redirect,output wire [63:0] redirect_target,
 output wire [2:0] kind,bytes
);
 wire hit,backward,bht_hit,bht_taken;
 wire [4:0] unused_index;wire [3:0] unused_history;
 rv64_btb #(.ENABLED(ENABLED)) target_copy(.clk(clk),.reset(reset),.clear(clear),.lookup_pc(pc),.hit(hit),.backward(backward),
  .kind(kind),.bytes(bytes),.target(target),.train(btb_train),.train_pc(train_pc),.train_next(train_next),.train_insn(train_insn),.train_bytes(train_bytes));
 rv64_bht #(.ENABLED(ENABLED!=0 && BHT_ENABLE!=0),.GSHARE_ENABLE(GSHARE_ENABLE)) directions(
  .clk(clk),.reset(reset),.clear(clear),.lookup_pc(pc),.hit(bht_hit),.taken(bht_taken),.lookup_index(unused_index),.global_history(unused_history),
  .train(bht_train),.train_taken(train_taken),.train_index(train_index),.train_pc(train_pc));
 wire taken=kind!=1 || (bht_hit ? bht_taken : backward);
 wire [63:0] destination=kind==3 && ras_valid ? ras_target : target;
 wire eligible=ENABLED!=0 && pc[1:0]==0 && hit && (bytes==2 || bytes==4);
 wire same_page=destination[63:12]==pc[63:12];
 assign page_block=eligible && taken && !same_page;
 assign hint=eligible && (!taken || (destination[1:0]==0 && same_page));
 // A taken same-page target can equal fall-through only if PC+4 stays
 // in this page. Both addresses are word-aligned when the hint is valid.
 wire [10:0] next_word={1'b0,pc[11:2]}+11'd1;
 assign redirect=hint && taken && (next_word[10] || destination[11:2]!=next_word[9:0]);
 assign redirect_target=destination;
 assign next_pc=hint && taken ? destination : pc+4;
endmodule
