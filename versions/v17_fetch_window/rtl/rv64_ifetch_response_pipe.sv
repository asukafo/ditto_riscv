// Elastic response stage in the instruction service pipeline. No redirect clear:
// every accepted old request must still complete to its poisoned owner slot.
module rv64_ifetch_response_pipe #(parameter ENABLED=1)(
 input wire clk,reset,u_valid,output wire u_ready,input wire [128:0] u_packet,
 output wire d_valid,input wire d_ready,output wire [128:0] d_packet
);
 reg valid;reg [128:0] packet;
 assign u_ready=ENABLED==0 ? d_ready : !valid || d_ready;
 assign d_valid=ENABLED==0 ? u_valid : valid;
 assign d_packet=ENABLED==0 ? u_packet : packet;
 always @(posedge clk)begin
  if(reset)begin valid<=0;packet<=0;end
  else if(ENABLED!=0 && u_ready)begin valid<=u_valid;if(u_valid)packet<=u_packet;end
 end
endmodule
