module rv64_decoder # (parameter EXTENSIONS=1) (
    input wire [31:0] insn,
    input wire [63:0] pc, a, b, alu_result,
    input wire [2:0] instruction_bytes,
    input wire alu_legal,
    output wire [4:0] rd, rs1, rs2,
    output wire [63:0] imm_i, address,
    output reg legal, write_rd, memory_op, csr_op, muldiv_op, atomic_op,
    output reg ecall, ebreak_op, mret, sret, wfi, sfence,
    output reg branch_taken,
    output reg [63:0] result, next_pc
);
    wire [11:0] imm_s={insn[31:25],insn[11:7]};
    wire [20:0] imm_b={{9{insn[31]}},insn[7],insn[30:25],insn[11:8],1'b0};
    wire [20:0] imm_j={insn[31],insn[19:12],insn[20],insn[30:21],1'b0};
    assign rd=insn[11:7]; assign rs1=insn[19:15]; assign rs2=insn[24:20];
    assign imm_i={{52{insn[31]}},insn[31:20]};
    // The low sum determines whether a signed 12-bit displacement changes
    // the upper bits. Form both upper neighbors in parallel with that sum.
    wire [11:0] displacement=insn[6:0]==7'h23 ? imm_s : imm_i[11:0];
    wire [12:0] low_sum={1'b0,a[11:0]}+{1'b0,displacement};
    wire [51:0] upper=a[63:12];
    wire [51:0] upper_sum=low_sum[12]==displacement[11] ? upper :
        low_sum[12] ? upper+52'd1 : upper-52'd1;
    wire [63:0] effective_address={upper_sum,low_sum[11:0]};
    assign address=atomic_op ? a : effective_address;
    wire [20:0] control_offset=insn[6:0]==7'h6f ? imm_j : imm_b;
    wire [21:0] control_low={1'b0,pc[20:0]}+{1'b0,control_offset};
    wire [42:0] control_high=pc[63:21];
    wire [42:0] target_high=control_low[21]==control_offset[20] ? control_high :
        control_low[21] ? control_high+43'd1 : control_high-43'd1;
    wire [63:0] direct_target={target_high,control_low[20:0]};
    always @* begin
        legal=1; write_rd=0; memory_op=0; csr_op=0; muldiv_op=0; atomic_op=0;
        ecall=0; ebreak_op=0; mret=0; sret=0; wfi=0; sfence=0; branch_taken=0;
        result=0; next_pc=pc+{61'd0,instruction_bytes};
        case (insn[6:0])
            7'h13,7'h1b,7'h33,7'h3b: begin
                muldiv_op=EXTENSIONS!=0 && (insn[6:0]==7'h33 || insn[6:0]==7'h3b) && insn[31:25]==1;
                legal=muldiv_op ? (insn[6:0]==7'h33 || insn[14:12]==0 || insn[14:12]>=4) : alu_legal;
                write_rd=1; result=alu_result;
            end
            7'h37,7'h17: begin
                write_rd=1; result={{32{insn[31]}},insn[31:12],12'b0};
                if (insn[6:0]==7'h17) result=pc+result;
            end
            7'h6f: begin write_rd=1; result=next_pc; next_pc=direct_target; end
            7'h67: begin legal=insn[14:12]==0; write_rd=1; result=next_pc; next_pc=effective_address&~64'd1; end
            7'h63: begin
                case (insn[14:12])
                    0: branch_taken=a==b;
                    1: branch_taken=a!=b;
                    4: branch_taken=$signed(a)<$signed(b);
                    5: branch_taken=$signed(a)>=$signed(b);
                    6: branch_taken=a<b;
                    7: branch_taken=a>=b;
                    default: legal=0;
                endcase
                if (branch_taken) next_pc=direct_target;
            end
            7'h03: begin legal=insn[14:12]!=7; memory_op=1; end
            7'h23: begin legal=!insn[14]; memory_op=1; end
            7'h2f: begin
                atomic_op=1; memory_op=1; write_rd=1;
                legal=EXTENSIONS!=0 && (insn[14:12]==2 || insn[14:12]==3);
                case (insn[31:27])
                    0,1,4,8,12,16,20,24,28: ;
                    2: legal=legal && rs2==0;
                    3: ;
                    default: legal=0;
                endcase
            end
            7'h0f: legal=insn[14:12]==0 || (EXTENSIONS!=0 && insn[14:12]==1);
            7'h73: begin
                if (insn[14:12]!=0) begin
                    csr_op=1; write_rd=1;
                    legal=EXTENSIONS!=0 && insn[14:12]!=4;
                end else begin
                    ecall=insn==32'h00000073; ebreak_op=insn==32'h00100073;
                    mret=insn==32'h30200073; sret=insn==32'h10200073; wfi=insn==32'h10500073;
                    sfence=insn[31:25]==7'h09 && rd==0;
                    legal=ecall || ebreak_op || (EXTENSIONS!=0 && (mret || sret || wfi || sfence));
                end
            end
            default: legal=0;
        endcase
    end
endmodule
