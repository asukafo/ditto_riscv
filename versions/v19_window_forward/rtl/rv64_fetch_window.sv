// Four address-tagged read slots. Ordered completion tokens are never reused
// until their response returns. Redirect poisons ownership; it does not cancel I/O.
module rv64_fetch_window #(parameter ENABLED=1,WINDOW_FORWARD=1,PREFETCH_PATH=1,EXTENSIONS=1,BTB_ENABLE=1,BHT_ENABLE=1,GSHARE_ENABLE=1,PREDICT_ENABLE=1)(
 input wire clk,reset,flush,allow,
 input wire predictor_clear,btb_train,bht_train,train_taken,
 input wire [63:0] train_pc,train_next,ras_target,input wire [31:0] train_insn,
 input wire [2:0] train_bytes,input wire [4:0] train_index,input wire ras_valid,
 output wire path_query_event,path_redirect_event,path_reject_event,path_page_block_event,
 input wire u_valid,output wire u_ready,input wire [63:0] u_addr,input wire [1:0] u_size,
 output wire u_rsp_valid,input wire u_rsp_ready,output wire [63:0] u_rsp_data,u_rsp_cause,output wire u_rsp_error,
 output wire d_valid,input wire d_ready,output wire [63:0] d_addr,output wire [1:0] d_size,
 input wire d_rsp_valid,output wire d_rsp_ready,input wire [63:0] d_rsp_data,d_rsp_cause,input wire d_rsp_error,
 output wire busy,output wire [2:0] pending,output wire hit_event,drop_event
);
 generate if(ENABLED==0)begin: bypass
 assign u_ready=d_ready;assign d_valid=u_valid;assign d_addr=u_addr;assign d_size=u_size;
 assign u_rsp_valid=d_rsp_valid;assign d_rsp_ready=u_rsp_ready;assign u_rsp_data=d_rsp_data;assign u_rsp_cause=d_rsp_cause;assign u_rsp_error=d_rsp_error;
 assign busy=0;assign pending=0;assign hit_event=0;assign drop_event=0;
 assign path_query_event=0;assign path_redirect_event=0;assign path_reject_event=0;assign path_page_block_event=0;
 wire unused=^{clk,reset,flush,allow,predictor_clear,btb_train,bht_train,train_taken,train_pc,train_next,ras_target,train_insn,train_bytes,train_index,ras_valid};
 end else begin: window
 reg [3:0] valid,issued,done,poison,error;
 reg [63:0] address[0:3],payload[0:3],causes[0:3];reg [1:0] sizes[0:3];
 reg [1:0] tokens[0:3],rh,rt,demand;
 reg [3:0] forecast_used;
 reg [63:0] forecast_next[0:3],forecast_target[0:3];
 reg [2:0] forecast_kind[0:3],forecast_bytes[0:3];
 reg [2:0] count;
 reg active,cancelled,speculate;
 reg [63:0] spec_pc;reg [51:0] spec_page;
 wire returned=d_rsp_valid && d_rsp_ready;
 wire [1:0] owner=tokens[rh];
 assign d_rsp_ready=count!=0;
 // The registered I response can feed its demand owner immediately. Do not
 // gate this on retarget: F may request a successor while consuming this word.
 // If F stalls, returned data is still captured below for a later retry.
 wire forward_return=WINDOW_FORWARD!=0 && active && valid[demand] && !done[demand] &&
  !poison[demand] && returned && owner==demand;
 assign u_rsp_valid=cancelled || (active && valid[demand] && !poison[demand] && (done[demand] || forward_return));
 assign u_rsp_data=cancelled ? 64'd0 : forward_return ? d_rsp_data : payload[demand];
 assign u_rsp_cause=cancelled ? 64'd1 : forward_return ? d_rsp_cause : causes[demand];
 assign u_rsp_error=cancelled || (forward_return ? d_rsp_error : error[demand]);
 wire consume=u_rsp_valid && u_rsp_ready;
 reg found,free_found,choose_found,exists;
 reg [1:0] match,free_slot,choose,existing_slot;
 integer j;
 wire retarget=u_valid && (!active || consume) && !found && !cancelled && allow && !flush;
 always @* begin
  found=0;match=0;free_found=0;free_slot=0;choose_found=0;choose=0;exists=0;existing_slot=0;
  for(integer k=0;k<4;k=k+1)begin
   if(valid[k] && !poison[k] && address[k]==u_addr && sizes[k]==u_size && !found)begin found=1;match=2'(k);end
  end
  for(integer k=0;k<4;k=k+1)begin
   if((!valid[k] || (retarget && (!issued[k] || done[k])) || (consume && !cancelled && demand==2'(k))) && !(u_valid && found && match==2'(k)) && !free_found)begin free_found=1;free_slot=2'(k);end
   if(valid[k] && !poison[k] && address[k]==spec_pc && sizes[k]==2)begin exists=1;existing_slot=2'(k);end
  end
  if(active && valid[demand] && !issued[demand] && !poison[demand])begin choose_found=1;choose=demand;end
  for(integer k=0;k<4;k=k+1)if(valid[k] && !issued[k] && !poison[k] && !choose_found)begin choose_found=1;choose=2'(k);end
 end
 assign u_ready=!reset && allow && !flush && !cancelled && (!active || consume) && (found || free_found);
 wire take=u_valid && u_ready;
 wire new_demand=take && !found;
 wire advance=!reset && !flush && !(take && !found) && allow && !retarget && active && speculate && spec_pc[63:12]==spec_page && (exists || free_found);
 wire allocate=advance && !exists;
 wire [63:0] path_pc=new_demand ? u_addr : spec_pc;
 wire path_eligible=!new_demand || (u_size==2 && u_addr[1:0]==0);
 wire hint,page_block;wire [63:0] hint_next,hint_target;wire [2:0] hint_kind,hint_bytes;
 rv64_prefetch_predictor #(.ENABLED(PREFETCH_PATH!=0 && BTB_ENABLE!=0 && PREDICT_ENABLE!=0),.BHT_ENABLE(BHT_ENABLE),.GSHARE_ENABLE(GSHARE_ENABLE)) path_predictor(
  .clk(clk),.reset(reset),.clear(predictor_clear),.pc(path_pc),.btb_train(btb_train),.bht_train(bht_train),.train_taken(train_taken),
  .train_pc(train_pc),.train_next(train_next),.train_insn(train_insn),.train_bytes(train_bytes),.train_index(train_index),.ras_valid(ras_valid),.ras_target(ras_target),
  .hint(hint),.page_block(page_block),.next_pc(hint_next),.target(hint_target),.kind(hint_kind),.bytes(hint_bytes));
 wire path_on=PREFETCH_PATH!=0 && BTB_ENABLE!=0 && PREDICT_ENABLE!=0;
 wire use_hint=path_on && path_eligible && hint;
 wire [63:0] chosen_next=use_hint ? hint_next : path_pc+4;
 // An existing slot retains the forecast made when it was allocated.
 wire [63:0] following=path_on && exists ? forecast_next[existing_slot] : chosen_next;
 assign path_query_event=path_on && path_eligible && (new_demand || allocate);
 assign path_redirect_event=path_query_event && chosen_next!=path_pc+4;
 assign path_page_block_event=path_query_event && page_block;
 wire [31:0] expanded;
 wire bad_compressed;
 rv64_decompress expand(.c(d_rsp_data[15:0]),.instruction(expanded),.illegal(bad_compressed));
 wire compressed=EXTENSIONS!=0 && d_rsp_data[1:0]!=3;
 wire [31:0] actual_insn=compressed ? expanded : d_rsp_data[31:0];
 wire actual_return=actual_insn[6:0]==7'h67 && actual_insn[14:12]==0 && actual_insn[11:7]==0 &&
  (actual_insn[19:15]==1 || actual_insn[19:15]==5) && actual_insn[31:20]==0;
 wire [2:0] actual_kind=actual_insn[6:0]==7'h63 && (actual_insn[14:12]<=1 || actual_insn[14:12]>=4) ? 3'd1 :
  actual_insn[6:0]==7'h6f ? 3'd2 : actual_insn[6:0]==7'h67 && actual_insn[14:12]==0 ? (actual_return ? 3'd3 : 3'd4) : 3'd0;
 wire [63:0] bo={{51{actual_insn[31]}},actual_insn[31],actual_insn[7],actual_insn[30:25],actual_insn[11:8],1'b0};
 wire [63:0] jo={{43{actual_insn[31]}},actual_insn[31],actual_insn[19:12],actual_insn[20],actual_insn[30:21],1'b0};
 wire metadata_ok=!d_rsp_error && !(compressed && bad_compressed) && actual_kind==forecast_kind[owner] &&
  (compressed ? 3'd2 : 3'd4)==forecast_bytes[owner] &&
  (actual_kind!=1 || address[owner]+bo==forecast_target[owner]) &&
  (actual_kind!=2 || address[owner]+jo==forecast_target[owner]);
 assign path_reject_event=returned && !poison[owner] && !flush && !retarget && forecast_used[owner] && !metadata_ok;
 assign d_valid=!reset && allow && !flush && !retarget && choose_found && (count<4 || returned);
 assign d_addr=address[choose];assign d_size=sizes[choose];
 wire send=d_valid && d_ready;
 assign pending=count;
 assign busy=count!=0;
 assign hit_event=take && found;
 assign drop_event=returned && (poison[owner] || flush || retarget);
 always @(posedge clk)begin
  if(reset)begin
   forecast_used<=0;valid<=0;issued<=0;done<=0;poison<=0;error<=0;rh<=0;rt<=0;count<=0;demand<=0;active<=0;cancelled<=0;speculate<=0;spec_pc<=0;spec_page<=0;
   for(j=0;j<4;j=j+1)begin address[j]<=0;payload[j]<=0;causes[j]<=0;sizes[j]<=0;tokens[j]<=0;forecast_next[j]<=0;forecast_target[j]<=0;forecast_kind[j]<=0;forecast_bytes[j]<=0;end
  end else begin

   if(consume)begin if(cancelled)cancelled<=0;else begin active<=0;valid[demand]<=0;end end
   if(flush || retarget)begin
    for(j=0;j<4;j=j+1)if(valid[j])begin if(issued[j] && !done[j])poison[j]<=1;else valid[j]<=0;end
    speculate<=0;
   end
   if(returned)begin
    rh<=rh+1'b1;
    if(poison[owner] || flush || retarget)valid[owner]<=0;
    else begin done[owner]<=1;payload[owner]<=d_rsp_data;causes[owner]<=d_rsp_cause;error[owner]<=d_rsp_error;end
   end
   if(send)begin issued[choose]<=1;tokens[rt]<=choose;rt<=rt+1'b1;end
   case({send,returned})2'b10:count<=count+1'b1;2'b01:count<=count-1'b1;default:;endcase
   if(flush)begin
    if(active && !consume)cancelled<=1;
    active<=0;speculate<=0;
   end else if(take)begin
    active<=1;demand<=found ? match : free_slot;
    if(found)valid[match]<=1;
    else begin valid[free_slot]<=1;issued[free_slot]<=0;done[free_slot]<=0;poison[free_slot]<=0;address[free_slot]<=u_addr;sizes[free_slot]<=u_size;end
    if(!found)begin spec_pc<=chosen_next;spec_page<=u_addr[63:12];speculate<=u_size==2 && u_addr[1:0]==0;end
   end
   if(!flush && !(take && !found) && allow && !retarget && active && speculate && spec_pc[63:12]==spec_page)begin
    if(exists)spec_pc<=path_on ? forecast_next[existing_slot] : spec_pc+4;
    else if(free_found)begin
     valid[free_slot]<=1;issued[free_slot]<=0;done[free_slot]<=0;poison[free_slot]<=0;address[free_slot]<=spec_pc;sizes[free_slot]<=2;
     spec_pc<=following;
    end
   end
   if(new_demand || allocate)begin
    forecast_used[free_slot]<=use_hint;forecast_next[free_slot]<=chosen_next;forecast_target[free_slot]<=hint_target;
    forecast_kind[free_slot]<=hint_kind;forecast_bytes[free_slot]<=hint_bytes;
   end
   // A bad forecast only stops further prefetch. It never cancels the demanded
   // read or changes the returned instruction; F/X retain architectural recovery.
   if(path_reject_event)speculate<=0;

  end
 end
 end endgenerate
endmodule
