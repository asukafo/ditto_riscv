// Full virtual-PC tag above the 32 halfword slots. Only retired controls allocate.
module rv64_btb #(parameter ENABLED=1) (
    input wire clk,reset,clear,input wire [63:0] lookup_pc,
    output wire hit,backward,output wire [2:0] kind,bytes,output wire [63:0] target,
    input wire train,input wire [63:0] train_pc,train_next,input wire [31:0] train_insn,
    input wire [2:0] train_bytes
);
    reg [31:0] valid;
    reg [57:0] tags [0:31];
    reg [63:0] targets [0:31];
    reg [2:0] kinds [0:31],lengths [0:31];
    reg [31:0] backwards;
    wire [4:0] ri=lookup_pc[5:1],wi=train_pc[5:1];
    wire branch=train_insn[6:0]==7'h63 && (train_insn[14:12]<=1 || train_insn[14:12]>=4);
    wire jal=train_insn[6:0]==7'h6f;
    wire jalr=train_insn[6:0]==7'h67 && train_insn[14:12]==0;
    wire ret=jalr && train_insn[11:7]==0 && (train_insn[19:15]==1 || train_insn[19:15]==5) && train_insn[31:20]==0;
    wire [63:0] bo={{51{train_insn[31]}},train_insn[31],train_insn[7],train_insn[30:25],train_insn[11:8],1'b0};
    wire [63:0] jo={{43{train_insn[31]}},train_insn[31],train_insn[19:12],train_insn[20],train_insn[30:21],1'b0};
    assign hit=ENABLED!=0 && !lookup_pc[0] && valid[ri] && tags[ri]==lookup_pc[63:6];
    assign kind=hit ? kinds[ri] : 3'd0;
    assign bytes=hit ? lengths[ri] : 3'd0;
    assign target=hit ? targets[ri] : 64'd0;
    assign backward=hit && backwards[ri];
    integer i;
    always @(posedge clk) begin
        if (reset || clear || ENABLED==0) begin
            valid<=0; backwards<=0;
            for(i=0;i<32;i=i+1) begin tags[i]<=0;targets[i]<=0;kinds[i]<=0;lengths[i]<=0;end
        end else if(train && !train_pc[0] && (train_bytes==2 || train_bytes==4) && (branch || jal || jalr)) begin
            valid[wi]<=1;tags[wi]<=train_pc[63:6];lengths[wi]<=train_bytes;
            kinds[wi]<=branch ? 3'd1 : jal ? 3'd2 : ret ? 3'd3 : 3'd4;
            targets[wi]<=branch ? train_pc+bo : jal ? train_pc+jo : train_next;
            backwards[wi]<=branch && train_insn[31];
        end
    end
endmodule
