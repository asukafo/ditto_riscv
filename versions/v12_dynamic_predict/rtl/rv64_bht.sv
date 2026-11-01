// Untagged bimodal table: aliases intentionally share history. No speculative writes.
module rv64_bht #(parameter ENABLED=1) (
    input wire clk,reset,clear,
    input wire [63:0] lookup_pc,
    output wire hit,taken,
    input wire train,train_taken,
    input wire [63:0] train_pc
);
    reg [31:0] valid;
    reg [1:0] counters [0:31];
    wire [4:0] read_index=lookup_pc[5:1],write_index=train_pc[5:1];
    wire unused_pc=^{lookup_pc[63:6],lookup_pc[0],train_pc[63:6],train_pc[0]};
    assign hit=ENABLED!=0 && valid[read_index];
    assign taken=hit && counters[read_index][1];
    integer i;
    always @(posedge clk) begin
        if (reset || clear || ENABLED==0) begin
            valid<=0;
            for (i=0;i<32;i=i+1) counters[i]<=1;
        end else if (train) begin
            valid[write_index]<=1;
            if (!valid[write_index]) counters[write_index]<=train_taken ? 2'd2 : 2'd1;
            else if (train_taken && counters[write_index]!=3) counters[write_index]<=counters[write_index]+1'b1;
            else if (!train_taken && counters[write_index]!=0) counters[write_index]<=counters[write_index]-1'b1;
        end
    end
endmodule
