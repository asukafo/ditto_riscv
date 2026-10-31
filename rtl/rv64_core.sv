// Modular multi-cycle RV64IMAC M/S/U core. HOST_TRAPS is only a legacy test configuration.
module rv64_core # (parameter EXTENSIONS=1, HOST_TRAPS=0) (
    input wire clk, input wire reset,
    input wire [63:0] irq_pending,time_value,
    input wire reservation_invalidate,
    output wire bus_lock,extended_mode,host_traps_enabled,
    output wire [63:0] debug_t3,
    output reg trap_valid, output reg [2:0] commit_bytes,
    output reg [63:0] trap_target,
    output reg [1:0] commit_privilege,
    output wire [1:0] current_privilege,
    output reg commit_mem_atomic, output reg [4:0] commit_mem_amo,
    output wire req_valid, input wire req_ready,
    output wire [63:0] req_addr, output wire req_write,
    output wire [63:0] req_wdata,
    output wire [1:0] req_size, // log2(bytes); payload starts at req_addr, unshifted
    output wire req_store_check, // failed SC permission probe; target checks store PMA without writing
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
    localparam [3:0] FETCH_REQ=0,FETCH_RSP=1,EXEC=2,DATA_REQ=3,DATA_RSP=4,STOP=5,
                     MD_WAIT=6,FETCH_HIGH_REQ=7,FETCH_HIGH_RSP=8;
    reg [3:0] state;
    reg [63:0] pc,mem_addr,mem_wdata;
    reg [31:0] insn,raw_insn;
    reg [15:0] low_half;
    reg [2:0] instruction_bytes;
    reg compressed_illegal,mem_write,mem_unsigned,mem_atomic;
    reg [4:0] mem_rd,mem_amo;
    reg [1:0] mem_size;
    wire [4:0] rd,rs1,rs2;
    wire [63:0] a,b,imm_i,address,alu_result,decoded_result,decoded_next;
    wire legal,alu_legal,write_rd,memory_op,csr_op,muldiv_op,atomic_op;
    wire ecall,ebreak_op,mret,sret,wfi,sfence;
    wire [63:0] load_result,raw_value,store_value,amo_new_value;
    wire [63:0] csr_read,return_pc,trap_vector,satp;
    wire csr_illegal,system_illegal,sum,mxr,interrupt_valid;
    wire [1:0] privilege,data_privilege;
    wire [63:0] interrupt_cause;
    wire md_busy,md_done;
    wire [63:0] md_result;
    wire [31:0] decompressed;
    wire decompression_illegal;
    wire [63:0] effective_next=(mret || sret) ? return_pc : decoded_next;
    wire decoded_write=atomic_op ? insn[31:27]!=2 : insn[6:0]==7'h23;
    wire [63:0] alignment_mask=(64'd1<<insn[13:12])-1;
    wire interrupt_take=EXTENSIONS!=0 && state==FETCH_REQ && interrupt_valid;
    reg take_trap;
    reg [2:0] trap_fault;
    reg [63:0] cause,value;
    wire retire=(state==EXEC && !take_trap && !memory_op && !muldiv_op) ||
        (state==DATA_RSP && v_rsp_valid && !v_rsp_error) || (state==MD_WAIT && md_done);
    wire memory_retire=state==DATA_RSP;
    wire sc=mem_atomic && mem_amo==3;
    wire sc_success=sc && v_rsp_data==0;
    wire [63:0] writeback=memory_retire ? (sc ? v_rsp_data : load_result) : state==MD_WAIT ? md_result : csr_op ? csr_read : decoded_result;
    wire [4:0] writeback_rd=memory_retire ? mem_rd : rd;
    wire writeback_enable=retire && (memory_retire ? (!mem_write || mem_atomic) : write_rd) && writeback_rd!=0;
    wire [63:0] retire_next=memory_retire || state==MD_WAIT ? pc+{61'd0,instruction_bytes} : effective_next;
    wire [63:0] retired_mem_data=mem_atomic ? (sc ? (sc_success ? store_value : 64'd0) : mem_amo==2 ? raw_value : amo_new_value) : mem_write ? store_value : raw_value;
    assign extended_mode=EXTENSIONS!=0; assign host_traps_enabled=HOST_TRAPS!=0;
    assign current_privilege=privilege;

    rv64_regfile registers(.clk(clk),.reset(reset),.write_enable(writeback_enable),.rs1(rs1),.rs2(rs2),
        .rd(writeback_rd),.write_data(writeback),.a(a),.b(b),.debug_t3(debug_t3));
    rv64_alu alu(.insn(insn),.a(a),.b(b),.imm_i(imm_i),.legal(alu_legal),.result(alu_result));
    rv64_decoder #(.EXTENSIONS(EXTENSIONS)) decoder(.insn(insn),.pc(pc),.a(a),.b(b),.alu_result(alu_result),
        .instruction_bytes(instruction_bytes),.alu_legal(alu_legal),.rd(rd),.rs1(rs1),.rs2(rs2),.imm_i(imm_i),.address(address),
        .legal(legal),.write_rd(write_rd),.memory_op(memory_op),.csr_op(csr_op),.muldiv_op(muldiv_op),.atomic_op(atomic_op),
        .ecall(ecall),.ebreak_op(ebreak_op),.mret(mret),.sret(sret),.wfi(wfi),.sfence(sfence),
        .result(decoded_result),.next_pc(decoded_next));
    rv64_lsu lsu(.raw_data(v_rsp_data),.store_data(mem_wdata),.size(mem_size),.unsigned_load(mem_unsigned),
        .load_result(load_result),.raw_value(raw_value),.store_value(store_value));
    rv64_amo_alu commit_atomic(.old_value(v_rsp_data),.operand(mem_wdata),.word_op(mem_size==2),.operation(mem_amo),.new_value(amo_new_value));
    rv64_muldiv muldiv(.clk(clk),.reset(reset),.start(state==EXEC && muldiv_op && !take_trap && !md_busy),
        .word_op(insn[6:0]==7'h3b),.operation(insn[14:12]),.a(a),.b(b),.busy(md_busy),.done(md_done),.result(md_result));
    rv64_decompress decompress(.c(v_rsp_data[15:0]),.instruction(decompressed),.illegal(decompression_illegal));
    rv64_csr #(.EXTENSIONS(EXTENSIONS)) csrs(.clk(clk),.reset(reset),.retire(retire),.irq_pending(irq_pending),.time_value(time_value),
        .csr_request(csr_op),.csr_commit(retire && csr_op),.address(insn[31:20]),.command(insn[14:12]),.source_index(rs1),.source_value(a),
        .read_data(csr_read),.illegal(csr_illegal),.mret(mret),.sret(sret),.wfi(wfi),.sfence(sfence),
        .return_commit(retire && (mret || sret)),.system_illegal(system_illegal),.return_pc(return_pc),
        .trap(take_trap && EXTENSIONS!=0 && HOST_TRAPS==0),.exception_pc(pc),.exception_cause(cause),.exception_value(value),
        .vector(trap_vector),.privilege(privilege),.data_privilege(data_privilege),.satp(satp),.sum(sum),.mxr(mxr),
        .interrupt_valid(interrupt_valid),.interrupt_cause(interrupt_cause));

    wire fetching=state==FETCH_REQ || state==FETCH_RSP || state==FETCH_HIGH_REQ || state==FETCH_HIGH_RSP;
    wire [63:0] fetch_address=pc+((state==FETCH_HIGH_REQ || state==FETCH_HIGH_RSP) ? 64'd2 : 64'd0);
    wire v_valid=!reset && !interrupt_take && (state==FETCH_REQ || state==FETCH_HIGH_REQ || state==DATA_REQ);
    wire v_ready,v_rsp_valid,v_rsp_error;
    wire v_rsp_ready=!reset && (state==FETCH_RSP || state==FETCH_HIGH_RSP || state==DATA_RSP);
    wire [63:0] v_rsp_data,v_rsp_cause;
    wire p_valid,p_ready,p_write,p_atomic,p_rsp_valid,p_rsp_ready,p_rsp_error;
    wire [63:0] p_addr,p_data,p_rsp_data;
    wire [1:0] p_size;
    wire [4:0] p_amo;
    rv64_mmu mmu(.clk(clk),.reset(reset),.privilege(privilege),.data_privilege(data_privilege),.satp(satp),.sum(sum),.mxr(mxr),
        .u_valid(v_valid),.u_ready(v_ready),.u_addr(fetching ? fetch_address : mem_addr),.u_data(mem_wdata),
        .u_size(fetching ? (EXTENSIONS!=0 ? 2'd1 : 2'd2) : mem_size),.u_write(!fetching && mem_write),
        .u_execute(fetching),.u_atomic(!fetching && mem_atomic),.u_amo(mem_amo),
        .u_rsp_valid(v_rsp_valid),.u_rsp_ready(v_rsp_ready),.u_rsp_data(v_rsp_data),.u_rsp_error(v_rsp_error),.u_rsp_cause(v_rsp_cause),
        .d_valid(p_valid),.d_ready(p_ready),.d_addr(p_addr),.d_data(p_data),.d_size(p_size),.d_write(p_write),.d_atomic(p_atomic),.d_amo(p_amo),
        .d_rsp_valid(p_rsp_valid),.d_rsp_ready(p_rsp_ready),.d_rsp_data(p_rsp_data),.d_rsp_error(p_rsp_error));
    rv64_atomic_adapter atomics(.clk(clk),.reset(reset),.clear_reservation(reservation_invalidate || take_trap || (retire && (mret || sret || sfence))),
        .u_valid(p_valid),.u_ready(p_ready),.u_addr(p_addr),.u_data(p_data),.u_write(p_write),.u_atomic(p_atomic),.u_amo(p_amo),.u_size(p_size),
        .u_rsp_valid(p_rsp_valid),.u_rsp_ready(p_rsp_ready),.u_rsp_data(p_rsp_data),.u_rsp_error(p_rsp_error),
        .d_valid(req_valid),.d_ready(req_ready),.d_addr(req_addr),.d_data(req_wdata),.d_write(req_write),.d_store_check(req_store_check),.d_size(req_size),
        .d_rsp_valid(rsp_valid),.d_rsp_ready(rsp_ready),.d_rsp_data(rsp_rdata),.d_rsp_error(rsp_error),.bus_lock(bus_lock));

    always @* begin
        take_trap=0; trap_fault=0; cause=0; value=0;
        if (interrupt_take) begin take_trap=1; cause=interrupt_cause; end
        else if ((state==FETCH_RSP || state==FETCH_HIGH_RSP) && v_rsp_valid && v_rsp_error) begin
            take_trap=1; trap_fault=3; cause=v_rsp_cause; value=fetch_address;
        end else if (state==EXEC) begin
            if (!legal || compressed_illegal || csr_illegal || system_illegal) begin
                take_trap=1; trap_fault=1; cause=2; value={32'd0,raw_insn};
            end else if (ecall || ebreak_op) begin
                take_trap=1; trap_fault=ecall ? 3'd4 : 3'd5;
                cause=ebreak_op ? 64'd3 : privilege==3 ? 64'd11 : privilege==1 ? 64'd9 : 64'd8;
            end else if ((EXTENSIONS!=0 ? effective_next[0] : |effective_next[1:0])) begin
                take_trap=1; trap_fault=2; cause=0; value=effective_next;
            end else if (memory_op && (address & alignment_mask)!=0) begin
                take_trap=1; trap_fault=2; cause=decoded_write ? 64'd6 : 64'd4; value=address;
            end
        end else if (state==DATA_RSP && v_rsp_valid && v_rsp_error) begin
            take_trap=1; trap_fault=3; cause=v_rsp_cause; value=mem_addr;
        end
    end
    always @(posedge clk) begin
        if (reset) begin
            state<=FETCH_REQ; pc<=0; insn<=0; raw_insn<=0; low_half<=0; instruction_bytes<=4; compressed_illegal<=0;
            halted<=0; fault<=0; trap_valid<=0; trap_pc<=0; trap_cause<=0; trap_value<=0;
            trap_target<=0; commit_privilege<=3;
            cycles<=0; instret<=0; fetch_wait<=0; data_wait<=0;
            mem_addr<=0; mem_wdata<=0; mem_write<=0; mem_unsigned<=0; mem_atomic<=0; mem_rd<=0; mem_size<=0; mem_amo<=0;
            commit_valid<=0; commit_pc<=0; commit_insn<=0; commit_rd_wen<=0; commit_rd<=0; commit_wdata<=0; commit_next_pc<=0;
            commit_mem_valid<=0; commit_mem_write<=0; commit_mem_addr<=0; commit_mem_data<=0; commit_mem_size<=0;
            commit_mem_atomic<=0; commit_mem_amo<=0; commit_bytes<=4;
        end else begin
            commit_valid<=0; trap_valid<=0; commit_rd_wen<=0; commit_rd<=0; commit_wdata<=0;
            commit_mem_valid<=0; commit_mem_write<=0; commit_mem_addr<=0; commit_mem_data<=0; commit_mem_size<=0;
            commit_mem_atomic<=0; commit_mem_amo<=0;
            if (!halted) cycles<=cycles+1;
            if (take_trap) begin
                trap_valid<=1; trap_pc<=pc; trap_cause<=cause; trap_value<=value;
                trap_target<=trap_vector;
                if (HOST_TRAPS!=0) begin halted<=1; fault<=trap_fault; state<=STOP; end
                else begin pc<=trap_vector; state<=FETCH_REQ; end
            end else begin
                if (retire) begin
                    commit_valid<=1; commit_pc<=pc; commit_insn<=raw_insn; commit_next_pc<=retire_next; commit_bytes<=instruction_bytes;
                    commit_privilege<=privilege;
                    commit_rd_wen<=writeback_enable; commit_rd<=writeback_enable ? writeback_rd : 5'd0;
                    commit_wdata<=writeback_enable ? writeback : 64'd0;
                    instret<=instret+1; pc<=retire_next; state<=FETCH_REQ;
                    if (memory_retire) begin
                        commit_mem_valid<=1; commit_mem_write<=mem_write && (!sc || sc_success);
                        commit_mem_addr<=mem_addr; commit_mem_data<=retired_mem_data; commit_mem_size<=mem_size;
                        commit_mem_atomic<=mem_atomic; commit_mem_amo<=mem_atomic ? mem_amo : 5'd0;
                    end
                end else case (state)
                    FETCH_REQ: if (v_valid && v_ready) state<=FETCH_RSP;
                    FETCH_RSP: begin
                        if (v_rsp_valid) begin
                            if (EXTENSIONS!=0 && v_rsp_data[1:0]==3) begin low_half<=v_rsp_data[15:0]; state<=FETCH_HIGH_REQ; end
                            else begin
                                insn<=EXTENSIONS!=0 ? decompressed : v_rsp_data[31:0];
                                raw_insn<=EXTENSIONS!=0 ? {16'd0,v_rsp_data[15:0]} : v_rsp_data[31:0];
                                instruction_bytes<=EXTENSIONS!=0 ? 3'd2 : 3'd4;
                                compressed_illegal<=EXTENSIONS!=0 && decompression_illegal; state<=EXEC;
                            end
                        end else fetch_wait<=fetch_wait+1;
                    end
                    FETCH_HIGH_REQ: if (v_valid && v_ready) state<=FETCH_HIGH_RSP;
                    FETCH_HIGH_RSP: begin
                        if (v_rsp_valid) begin
                            insn<={v_rsp_data[15:0],low_half}; raw_insn<={v_rsp_data[15:0],low_half};
                            instruction_bytes<=4; compressed_illegal<=0; state<=EXEC;
                        end else fetch_wait<=fetch_wait+1;
                    end
                    EXEC: begin
                        if (memory_op) begin
                            mem_addr<=address; mem_wdata<=b; mem_rd<=rd; mem_size<=insn[13:12];
                            mem_write<=decoded_write; mem_unsigned<=!atomic_op && insn[14];
                            mem_atomic<=atomic_op; mem_amo<=insn[31:27]; state<=DATA_REQ;
                        end else if (muldiv_op) state<=MD_WAIT;
                    end
                    DATA_REQ: if (v_valid && v_ready) state<=DATA_RSP;
                    DATA_RSP: if (!v_rsp_valid) data_wait<=data_wait+1;
                    default: ;
                endcase
            end
        end
    end
endmodule
