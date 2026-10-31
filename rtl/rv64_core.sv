// Multi-cycle RV64I execution core; terminal traps are handled by the host EEI.
module rv64_core (
    input wire clk, input wire reset,
    output wire req_valid, input wire req_ready,
    output wire [63:0] req_addr, output wire req_write,
    output wire [63:0] req_wdata,
    output wire [1:0] req_size, // log2(bytes); payload starts at req_addr, unshifted
    input wire rsp_valid, output wire rsp_ready,
    input wire [63:0] rsp_rdata, input wire rsp_error,
    output reg halted, output reg [2:0] fault,
    output reg [63:0] trap_pc, output reg [63:0] trap_cause, output reg [63:0] trap_value,
    output reg [63:0] cycles, output reg [63:0] instret,
    output reg [63:0] fetch_wait, output reg [63:0] data_wait,
    output reg commit_valid, output reg [63:0] commit_pc,
    output reg [31:0] commit_insn,
    output reg commit_rd_wen, output reg [4:0] commit_rd,
    output reg [63:0] commit_wdata, output reg [63:0] commit_next_pc,
    output reg commit_mem_valid, output reg commit_mem_write,
    output reg [63:0] commit_mem_addr, output reg [63:0] commit_mem_data,
    output reg [1:0] commit_mem_size
);
    localparam [2:0] FETCH_REQ=0, FETCH_RSP=1, EXEC=2,
                     DATA_REQ=3, DATA_RSP=4, STOP=5;
    reg [2:0] state;
    reg [63:0] pc;
    reg [31:0] insn;
    reg [63:0] regs [0:31];
    reg [63:0] mem_addr, mem_wdata;
    reg mem_write;
    reg [4:0] mem_rd;
    reg [1:0] mem_size;
    reg mem_unsigned;
    wire [4:0] rd = insn[11:7];
    wire [4:0] rs1 = insn[19:15];
    wire [4:0] rs2 = insn[24:20];
    wire [63:0] a = (rs1 == 0) ? 64'd0 : regs[rs1];
    wire [63:0] b = (rs2 == 0) ? 64'd0 : regs[rs2];
    wire [63:0] imm_i = {{52{insn[31]}}, insn[31:20]};
    wire [63:0] imm_s = {{52{insn[31]}}, insn[31:25], insn[11:7]};
    wire [63:0] imm_b = {{51{insn[31]}}, insn[31], insn[7], insn[30:25], insn[11:8], 1'b0};
    wire [63:0] imm_j = {{43{insn[31]}}, insn[31], insn[19:12], insn[20], insn[30:21], 1'b0};
    wire [63:0] effective_addr = a + (insn[6:0] == 7'h23 ? imm_s : imm_i);
    reg legal, write_rd, memory_op, branch_taken, system_trap;
    reg [63:0] result, next_pc;
    reg [31:0] word_result;
    wire [1:0] decoded_size=insn[13:12];
    wire [63:0] alignment_mask=(64'd1<<decoded_size)-1;
    wire [63:0] load_result;
    integer i;

    function [63:0] sized_data;
        input [63:0] data;
        input [1:0] size;
        input unsigned_load;
        begin
            case (size)
                0: sized_data={{56{!unsigned_load && data[7]}}, data[7:0]};
                1: sized_data={{48{!unsigned_load && data[15]}}, data[15:0]};
                2: sized_data={{32{!unsigned_load && data[31]}}, data[31:0]};
                default: sized_data=data;
            endcase
        end
    endfunction
    assign load_result=sized_data(rsp_rdata, mem_size, mem_unsigned);

    assign req_valid = !reset && (state == FETCH_REQ || state == DATA_REQ);
    assign req_addr = (state == FETCH_REQ) ? pc : mem_addr;
    assign req_write = state == DATA_REQ && mem_write;
    assign req_wdata = mem_wdata;
    assign req_size = (state == FETCH_REQ) ? 2'd2 : mem_size;
    assign rsp_ready = !reset && (state == FETCH_RSP || state == DATA_RSP);

    // Decode only the documented subset; unsupported encodings fail explicitly.
    always @* begin
        legal=1; write_rd=0; memory_op=0; branch_taken=0; system_trap=0;
        result=0; word_result=0; next_pc=pc+64'd4;
        case (insn[6:0])
            7'h13: begin // RV64 OP-IMM: shift amount is six bits, not five.
                write_rd=1;
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
                write_rd=1;
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
                write_rd=1;
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
                write_rd=1;
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
            7'h37, 7'h17: begin // LUI / AUIPC
                write_rd=1; result={{32{insn[31]}}, insn[31:12], 12'b0};
                if (insn[6:0]==7'h17) result=pc+result;
            end
            7'h6f: begin // JAL
                write_rd=1; result=pc+64'd4; next_pc=pc+imm_j;
            end
            7'h67: begin // JALR uses the OLD rs1 value even when rd == rs1.
                legal=insn[14:12]==0;
                write_rd=1; result=pc+64'd4; next_pc=(a+imm_i)&~64'd1;
            end
            7'h63: begin
                case (insn[14:12])
                    3'b000: branch_taken=a==b;
                    3'b001: branch_taken=a!=b;
                    3'b100: branch_taken=$signed(a)<$signed(b);
                    3'b101: branch_taken=$signed(a)>=$signed(b);
                    3'b110: branch_taken=a<b;
                    3'b111: branch_taken=a>=b;
                    default: legal=0;
                endcase
                if (branch_taken) next_pc=pc+imm_b;
            end
            7'h03: begin // LB/LH/LW/LD/LBU/LHU/LWU
                legal=insn[14:12]!=3'b111; memory_op=1;
            end
            7'h23: begin // SB/SH/SW/SD
                legal=!insn[14]; memory_op=1;
            end
            7'h0f: begin // Conservative FENCE: all transactions already serialize.
                legal=insn[14:12]==0; // ignore fm, pred/succ, rs1 and rd per base ISA
            end
            7'h73: begin
                legal=insn==32'h00000073 || insn==32'h00100073;
                system_trap=1;
            end
            default: legal=0;
        endcase
    end

    always @(posedge clk) begin
        if (reset) begin
            state<=FETCH_REQ; pc<=0; insn<=0; halted<=0; fault<=0;
            trap_pc<=0; trap_cause<=0; trap_value<=0;
            cycles<=0; instret<=0; fetch_wait<=0; data_wait<=0;
            commit_valid<=0; commit_pc<=0; commit_insn<=0;
            commit_rd_wen<=0; commit_rd<=0; commit_wdata<=0; commit_next_pc<=0;
            commit_mem_valid<=0; commit_mem_write<=0; commit_mem_addr<=0; commit_mem_data<=0;
            commit_mem_size<=0;
            mem_addr<=0; mem_wdata<=0; mem_write<=0; mem_rd<=0;
            mem_size<=0; mem_unsigned<=0;
            for (i=0; i<32; i=i+1) regs[i]<=0;
        end else begin
            commit_valid<=0;
            commit_rd_wen<=0; commit_rd<=0; commit_wdata<=0;
            commit_mem_valid<=0; commit_mem_write<=0; commit_mem_addr<=0; commit_mem_data<=0;
            commit_mem_size<=0;
            regs[0]<=0;
            if (!halted) cycles<=cycles+1;
            case (state)
                FETCH_REQ: if (req_valid && req_ready) state<=FETCH_RSP;
                FETCH_RSP: begin
                    if (rsp_valid) begin
                        if (rsp_error) begin
                            halted<=1; fault<=3; state<=STOP;
                            trap_pc<=pc; trap_cause<=1; trap_value<=pc;
                        end
                        else begin insn<=rsp_rdata[31:0]; state<=EXEC; end
                    end else fetch_wait<=fetch_wait+1;
                end
                EXEC: begin
                    if (!legal) begin
                        halted<=1; fault<=1; state<=STOP;
                        trap_pc<=pc; trap_cause<=2; trap_value<={32'd0,insn};
                    end else if (system_trap) begin
                        halted<=1; fault<=insn[20] ? 3'd5 : 3'd4; state<=STOP;
                        trap_pc<=pc; trap_cause<=insn[20] ? 64'd3 : 64'd11; trap_value<=0;
                    end else if (next_pc[1:0]!=0) begin
                        halted<=1; fault<=2; state<=STOP;
                        trap_pc<=pc; trap_cause<=0; trap_value<=next_pc;
                    end else if (memory_op && (effective_addr & alignment_mask)!=0) begin
                        halted<=1; fault<=2; state<=STOP;
                        trap_pc<=pc; trap_cause<=insn[6:0]==7'h23 ? 64'd6 : 64'd4;
                        trap_value<=effective_addr;
                    end else if (memory_op) begin
                        mem_addr<=effective_addr; mem_wdata<=b;
                        mem_write<=insn[6:0]==7'h23; mem_rd<=rd; state<=DATA_REQ;
                        mem_size<=decoded_size; mem_unsigned<=insn[14];
                    end else begin
                        if (write_rd && rd!=0) regs[rd]<=result;
                        pc<=next_pc; instret<=instret+1;
                        commit_valid<=1; commit_pc<=pc; commit_insn<=insn;
                        commit_next_pc<=next_pc;
                        commit_rd_wen<=write_rd && rd!=0;
                        commit_rd<=(write_rd && rd!=0) ? rd : 5'd0;
                        commit_wdata<=(write_rd && rd!=0) ? result : 64'd0;
                        state<=FETCH_REQ;
                    end
                end
                DATA_REQ: if (req_valid && req_ready) state<=DATA_RSP;
                DATA_RSP: begin
                    if (rsp_valid) begin
                        if (rsp_error) begin
                            halted<=1; fault<=3; state<=STOP;
                            trap_pc<=pc; trap_cause<=mem_write ? 64'd7 : 64'd5; trap_value<=mem_addr;
                        end
                        else begin
                            if (!mem_write && mem_rd!=0) regs[mem_rd]<=load_result;
                            pc<=pc+4; state<=FETCH_REQ; instret<=instret+1;
                            commit_valid<=1; commit_pc<=pc; commit_insn<=insn;
                            commit_next_pc<=pc+4;
                            commit_rd_wen<=!mem_write && mem_rd!=0;
                            commit_rd<=(!mem_write && mem_rd!=0) ? mem_rd : 5'd0;
                            commit_wdata<=(!mem_write && mem_rd!=0) ? load_result : 64'd0;
                            commit_mem_valid<=1; commit_mem_write<=mem_write;
                            commit_mem_addr<=mem_addr;
                            commit_mem_data<=sized_data(mem_write ? mem_wdata : rsp_rdata, mem_size, 1'b1);
                            commit_mem_size<=mem_size;
                        end
                    end else data_wait<=data_wait+1;
                end
                default: state<=STOP;
            endcase
        end
    end
endmodule
