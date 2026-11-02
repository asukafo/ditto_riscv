// Four address-tagged read slots. Ordered completion tokens are never reused
// until their response returns. Redirect poisons ownership; it does not cancel I/O.
module rv64_fetch_window #(parameter ENABLED=1)(
 input wire clk,reset,flush,allow,
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
 wire unused=clk^reset^flush^allow;
 end else begin: window
 reg [3:0] valid,issued,done,poison,error;
 reg [63:0] address[0:3],payload[0:3],causes[0:3];reg [1:0] sizes[0:3];
 reg [1:0] tokens[0:3],rh,rt,demand;
 reg [2:0] count;
 reg active,cancelled,speculate;
 reg [63:0] spec_pc;reg [51:0] spec_page;
 wire returned=d_rsp_valid && d_rsp_ready;
 wire [1:0] owner=tokens[rh];
 assign d_rsp_ready=count!=0;
 assign u_rsp_valid=cancelled || (active && valid[demand] && done[demand] && !poison[demand]);
 assign u_rsp_data=cancelled ? 64'd0 : payload[demand];
 assign u_rsp_cause=cancelled ? 64'd1 : causes[demand];
 assign u_rsp_error=cancelled || error[demand];
 wire consume=u_rsp_valid && u_rsp_ready;
 reg found,free_found,choose_found,exists;
 reg [1:0] match,free_slot,choose;
 integer j;
 wire retarget=u_valid && (!active || consume) && !found && !cancelled && allow && !flush;
 always @* begin
  found=0;match=0;free_found=0;free_slot=0;choose_found=0;choose=0;exists=0;
  for(integer k=0;k<4;k=k+1)begin
   if(valid[k] && !poison[k] && address[k]==u_addr && sizes[k]==u_size && !found)begin found=1;match=2'(k);end
  end
  for(integer k=0;k<4;k=k+1)begin
   if((!valid[k] || (retarget && (!issued[k] || done[k])) || (consume && !cancelled && demand==2'(k))) && !(u_valid && found && match==2'(k)) && !free_found)begin free_found=1;free_slot=2'(k);end
   if(valid[k] && !poison[k] && address[k]==spec_pc && sizes[k]==2)exists=1;
  end
  if(active && valid[demand] && !issued[demand] && !poison[demand])begin choose_found=1;choose=demand;end
  for(integer k=0;k<4;k=k+1)if(valid[k] && !issued[k] && !poison[k] && !choose_found)begin choose_found=1;choose=2'(k);end
 end
 assign u_ready=!reset && allow && !flush && !cancelled && (!active || consume) && (found || free_found);
 wire take=u_valid && u_ready;
 assign d_valid=!reset && allow && !flush && !retarget && choose_found && (count<4 || returned);
 assign d_addr=address[choose];assign d_size=sizes[choose];
 wire send=d_valid && d_ready;
 assign pending=count;
 assign busy=count!=0;
 assign hit_event=take && found;
 assign drop_event=returned && (poison[owner] || flush || retarget);
 always @(posedge clk)begin
  if(reset)begin
   valid<=0;issued<=0;done<=0;poison<=0;error<=0;rh<=0;rt<=0;count<=0;demand<=0;active<=0;cancelled<=0;speculate<=0;spec_pc<=0;spec_page<=0;
   for(j=0;j<4;j=j+1)begin address[j]<=0;payload[j]<=0;causes[j]<=0;sizes[j]<=0;tokens[j]<=0;end
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
    if(!found)begin spec_pc<=u_addr+4;spec_page<=u_addr[63:12];speculate<=u_size==2 && u_addr[1:0]==0;end
   end
   if(!flush && !(take && !found) && allow && !retarget && active && speculate && spec_pc[63:12]==spec_page)begin
    if(exists)spec_pc<=spec_pc+4;
    else if(free_found)begin
     valid[free_slot]<=1;issued[free_slot]<=0;done[free_slot]<=0;poison[free_slot]<=0;address[free_slot]<=spec_pc;sizes[free_slot]<=2;
     spec_pc<=spec_pc+4;
    end
   end
  end
 end
 end endgenerate
endmodule
