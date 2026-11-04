// Static BTFNT after instruction assembly/decompression, without a BTB/history table.
module rv64_static_predictor #(parameter ENABLED=1, EXTENSIONS=1) (
    input wire [63:0] pc,input wire [31:0] insn,input wire [2:0] bytes,
    input wire legal,output wire [63:0] predicted_next
);
    wire [63:0] branch_offset={{51{insn[31]}},insn[31],insn[7],insn[30:25],insn[11:8],1'b0};
    wire [63:0] jump_offset={{43{insn[31]}},insn[31],insn[19:12],insn[20],insn[30:21],1'b0};
    wire conditional=insn[6:0]==7'h63 && (insn[14:12]<=1 || insn[14:12]>=4);
    wire direct_jump=insn[6:0]==7'h6f;
    wire [63:0] target=pc+(direct_jump ? jump_offset : branch_offset);
    wire aligned=EXTENSIONS!=0 ? !target[0] : target[1:0]==0;
    wire take=ENABLED!=0 && legal && aligned && (direct_jump || (conditional && insn[31]));
    assign predicted_next=take ? target : pc+{61'd0,bytes};
endmodule
