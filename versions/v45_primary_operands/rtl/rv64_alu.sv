// Ordinary RV64I integer ALU; multiply/divide has its own sequential unit.
module rv64_alu (
    input wire [31:0] insn, input wire [63:0] a, b, imm_i,
    output reg legal, output reg [63:0] result
);
    reg [31:0] word_result;
    wire unused_register_fields=^{insn[19:15],insn[11:7]};
    always @* begin
        legal=1; result=0; word_result=0;
        case (insn[6:0])
            7'h13: begin // RV64 OP-IMM: shift amount is six bits, not five.
                
                case (insn[14:12])
                    3'b000: result=a+imm_i;
                    3'b010: result=($signed(a)<$signed(imm_i)) ? 64'd1 : 64'd0;
                    3'b011: result=(a<imm_i) ? 64'd1 : 64'd0;
                    3'b100: result=a^imm_i;
                    3'b110: result=a|imm_i;
                    3'b111: result=a&imm_i;
                    3'b001: begin
                        legal=insn[31:26]==6'b000000;
                        result=a<<insn[25:20];
                    end
                    3'b101: begin
                        legal=insn[31:26]==6'b000000 || insn[31:26]==6'b010000;
                        if (insn[30]) result=$signed(a)>>>insn[25:20];
                        else result=a>>insn[25:20];
                    end
                    default: legal=0;
                endcase
            end
            7'h33: begin // RV64 OP: only rs2[5:0] is used as a shift amount.
                
                legal=insn[31:25]==0;
                case (insn[14:12])
                    3'b000: begin
                        legal=insn[31:25]==0 || insn[31:25]==7'h20;
                        result=insn[30] ? a-b : a+b;
                    end
                    3'b001: result=a<<b[5:0];
                    3'b010: result=($signed(a)<$signed(b)) ? 64'd1 : 64'd0;
                    3'b011: result=(a<b) ? 64'd1 : 64'd0;
                    3'b100: result=a^b;
                    3'b101: begin
                        legal=insn[31:25]==0 || insn[31:25]==7'h20;
                        if (insn[30]) result=$signed(a)>>>b[5:0];
                        else result=a>>b[5:0];
                    end
                    3'b110: result=a|b;
                    3'b111: result=a&b;
                    default: legal=0;
                endcase
            end
            7'h1b: begin // OP-IMM-32: always sign-extend the low 32-bit result.
                
                case (insn[14:12])
                    0: word_result=a[31:0]+imm_i[31:0];
                    1: begin
                        legal=insn[31:25]==0;
                        word_result=a[31:0]<<insn[24:20];
                    end
                    5: begin
                        legal=insn[31:25]==0 || insn[31:25]==7'h20;
                        if (insn[30]) word_result=$signed(a[31:0])>>>insn[24:20];
                        else word_result=a[31:0]>>insn[24:20];
                    end
                    default: legal=0;
                endcase
                result={{32{word_result[31]}}, word_result};
            end
            7'h3b: begin // OP-32: register shifts use only rs2[4:0].
                
                legal=insn[31:25]==0;
                case (insn[14:12])
                    0: begin
                        legal=insn[31:25]==0 || insn[31:25]==7'h20;
                        word_result=insn[30] ? a[31:0]-b[31:0] : a[31:0]+b[31:0];
                    end
                    1: word_result=a[31:0]<<b[4:0];
                    5: begin
                        legal=insn[31:25]==0 || insn[31:25]==7'h20;
                        if (insn[30]) word_result=$signed(a[31:0])>>>b[4:0];
                        else word_result=a[31:0]>>b[4:0];
                    end
                    default: legal=0;
                endcase
                result={{32{word_result[31]}}, word_result};
            end
            default: legal=0;
        endcase
    end
endmodule
