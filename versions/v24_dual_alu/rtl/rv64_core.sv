// In-order F/X/W core: full-ISA primary lane plus conservative simple-ALU pairing.
module rv64_core # (parameter EXTENSIONS=1, HOST_TRAPS=0, ICACHE_ENABLE=1, FETCH_BUFFER_ENABLE=1, EARLY_RESTART=1, DCACHE_ENABLE=1, DCACHE_EARLY_RESTART=1, SPLIT_MEMORY=1, PREDICT_ENABLE=1, RAS_ENABLE=1, TLB_ENABLE=1, BHT_ENABLE=1, GSHARE_ENABLE=1, BTB_ENABLE=1, FETCH_QUEUE_ENABLE=1, I_PIPELINE=1, FETCH_WINDOW=1, PREFETCH_PATH=1, WINDOW_FORWARD=1, DEMAND_ISSUE=1, DEMAND_PRIORITY=1, ICACHE_HIT_UNDER_REFILL=1, ICACHE_FILL_FORWARD=1, DUAL_ISSUE=1, PAIR_ENABLE=1) (
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
    output wire dual_issue_enabled,issue_lookahead_enabled,output wire [1:0] issue_pair_occupancy,
    output reg commit2_valid,output reg [63:0] commit2_pc,commit2_next_pc,commit2_wdata,
    output reg [31:0] commit2_insn,output reg [4:0] commit2_rd,output reg commit2_rd_wen,
    output reg [2:0] commit2_bytes,output reg [1:0] commit2_privilege,
    output reg [63:0] dual_issue_pairs,
    output reg commit_valid, output reg [63:0] commit_pc,
    output reg [31:0] commit_insn,
    output reg commit_rd_wen, output reg [4:0] commit_rd,
    output reg [63:0] commit_wdata, output reg [63:0] commit_next_pc,
    output reg commit_mem_valid, output reg commit_mem_write,
    output reg [63:0] commit_mem_addr, output reg [63:0] commit_mem_data,
    output reg [1:0] commit_mem_size,
    output reg [63:0] overlap_cycles,xw_overlap_cycles,issue_count,bypass_count,flush_count,
    output wire icache_enabled,icache_hit_event,icache_miss_event,icache_refill_event,icache_miss_wait,
    output wire icache_bypass_event,icache_invalidate_event,
    output wire frontend_starved,data_blocked_by_fetch,fetch_blocked_by_data,fetch_discard_event,
    output wire tlb_enabled,tlb_invalidate_event,itlb_hit_event,itlb_miss_event,itlb_fill_event,dtlb_hit_event,dtlb_miss_event,dtlb_fill_event,i_walk_event,d_walk_event,
    output wire ras_enabled,ras_prediction_event,ras_miss_event,ras_push_event,ras_pop_event,ras_overflow_event,ras_underflow_event,
    output wire icache_fill_forward_enabled,icache_fill_hit_event,
    output wire icache_refill_hits_enabled,icache_refill_hit_event,
    output wire demand_priority_enabled,demand_issue_enabled,window_forward_enabled,
    output wire prefetch_path_enabled,prefetch_path_query_event,prefetch_path_redirect_event,prefetch_path_reject_event,prefetch_path_page_block_event,
    output wire ifetch_window_enabled,ifetch_window_hit_event,ifetch_window_drop_event,
    output wire [2:0] ifetch_window_pending,
    output wire fetch_queue_fill_while_x_busy,
    output wire fetch_queue_enabled,fetch_queue_push_event,fetch_queue_pop_event,fetch_queue_bypass_event,fetch_queue_full_stall,fetch_queue_flush_event,
    output wire [2:0] fetch_queue_occupancy,
    output wire btb_enabled,btb_lookup_event,btb_hit_event,btb_train_event,btb_reject_event,btb_prediction_event,btb_miss_event,
    output wire gshare_enabled,
    output wire [3:0] global_history,
    output wire bht_enabled,bht_train_event,bht_taken_event,bht_prediction_event,bht_miss_event,
    output wire predictor_enabled,control_resolve_event,conditional_resolve_event,direct_jump_resolve_event,indirect_jump_resolve_event,
    output wire control_miss_event,predicted_redirect_event,
    output wire split_memory_enabled,icache_hit_during_data_fill,dcache_hit_during_instruction_fill,
    output wire dcache_enabled,dcache_hit_event,dcache_miss_event,dcache_refill_event,dcache_miss_wait,dcache_write_event,dcache_bypass_event,
    output wire fetch_buffer_enabled,fetch_buffer_reuse_event,fetch_buffer_flush_event
);
    localparam [2:0] EMPTY=0,EXEC=1,DATA_REQ=2,DATA_RSP=3,MD_WAIT=4;
    reg [2:0] state;
    reg [63:0] architectural_pc,pc,a,b,ex_predicted_next;
    reg [31:0] insn,raw_insn;
    reg [2:0] instruction_bytes;
    reg [4:0] ex_predicted_index,wb_predicted_index;
    wire [4:0] fe_predicted_index;
    reg ex_predicted_btb;
    wire fe_predicted_btb;
    wire [63:0] unused_fe_query_pc;
    reg ex_predicted_dynamic;
    reg compressed_illegal,fetch_fault,ex_predicted_return;
    reg [63:0] fetch_cause,fetch_value;
    reg [63:0] mem_addr,mem_wdata;
    reg mem_write,mem_unsigned,mem_atomic;
    reg [4:0] mem_rd,mem_amo;
    reg [1:0] mem_size;

    reg xp_valid,wb_pair;
    reg [63:0] xp_pc,xp_a,xp_b,wp_pc,wp_next,wp_result;
    reg [31:0] xp_insn,xp_raw,wp_raw;
    reg [2:0] xp_bytes,wp_bytes;reg [4:0] wp_rd;
    wire [63:0] xp_result=xp_insn[6:0]==7'h13 ? xp_a+{{52{xp_insn[31]}},xp_insn[31:20]} : xp_insn[30] ? xp_a-xp_b : xp_a+xp_b;
    wire [4:0] xp_rd=xp_insn[11:7];
    reg wb_branch_taken;
    reg wb_valid,wb_trap,wb_serial,wb_csr,wb_mret,wb_sret,wb_sfence;
    reg [2:0] wb_fault,wb_bytes;
    reg [63:0] wb_pc,wb_next,wb_result,wb_source,wb_cause,wb_value;
    reg [31:0] wb_insn,wb_raw;
    reg [1:0] wb_privilege;
    reg wb_rd_wen,wb_mem_valid,wb_mem_write,wb_mem_atomic;
    reg [4:0] wb_rd,wb_amo;
    reg [1:0] wb_size;
    reg [63:0] wb_mem_addr,wb_mem_data;

    wire [4:0] rd,rs1,rs2;
    wire [63:0] imm_i,address,alu_result,decoded_result,decoded_next;
    wire decoded_branch_taken;
    wire legal,alu_legal,write_rd,memory_op,csr_op,muldiv_op,atomic_op;
    wire ecall,ebreak_op,mret,sret,wfi,sfence;
    wire [63:0] csr_read,return_pc,trap_vector,satp;
    wire csr_illegal,system_illegal,sum,mxr,interrupt_valid;
    wire [1:0] privilege,data_privilege;
    wire [63:0] interrupt_cause;
    wire md_busy,md_done;
    wire [63:0] md_result;
    wire [63:0] effective_next=(mret || sret) ? return_pc : decoded_next;
    wire decoded_write=atomic_op ? insn[31:27]!=2 : insn[6:0]==7'h23;
    wire [63:0] alignment_mask=(64'd1<<insn[13:12])-1;
    wire ex_serial=insn[6:0]==7'h73 || insn[6:0]==7'h0f;

    wire fe_predicted_dynamic;
    wire fe_valid,fe_ready,fe_illegal,fe_fault,fe_waiting,fe_active,fe_predicted_return;
    wire [63:0] fe_pc,fe_cause,fe_value,fe_predicted_next;
    wire [31:0] fe_insn,fe_raw;
    wire [2:0] fe_bytes;
    wire f_valid,f_ready,arb_f_ready,f_rsp_valid,f_rsp_ready;
    wire [63:0] f_addr;
    wire [1:0] f_size;
    wire bus_busy,raw_bus_busy,window_busy;
    wire mw_valid,mw_ready,mw_rsp_valid,mw_rsp_ready,mw_rsp_error;
    wire mi_rsp_valid,mi_rsp_ready,mi_rsp_error;
    wire [63:0] mi_rsp_data,mi_rsp_cause;
    wire [63:0] mw_addr,mw_rsp_data,mw_rsp_cause;
    wire [1:0] mw_size;
    wire d_ready,d_rsp_valid;
    wire [63:0] v_rsp_data,v_rsp_cause;
    wire v_rsp_error;
    wire [63:0] f_rsp_data,f_rsp_cause;
    wire f_rsp_error;
    wire data_rsp_ready=state==DATA_RSP && (!wb_valid || wb_fire);
    wire irq_stop=EXTENSIONS!=0 && interrupt_valid;
    wire interrupt_take=!reset && !halted && irq_stop && state==EMPTY && !wb_valid && !bus_busy;
    wire wb_fire=!reset && !halted && wb_valid && (!(wb_serial || wb_trap) || !bus_busy);
    wire retire=wb_fire && !wb_trap;
    wire wb_redirect=wb_fire && (wb_serial || wb_trap);
    wire trap_enter=(wb_fire && wb_trap) || interrupt_take;
    wire [63:0] trap_exception_pc=interrupt_take ? architectural_pc : wb_pc;
    wire [63:0] trap_exception_cause=interrupt_take ? interrupt_cause : wb_cause;
    wire [63:0] trap_exception_value=interrupt_take ? 64'd0 : wb_value;
    wire [63:0] wb_writeback=wb_csr ? csr_read : wb_result;
    wire wb_write_enable=retire && wb_rd_wen && wb_rd!=0;
    wire serialize_pending=(state!=EMPTY && ex_serial) || (wb_valid && (wb_serial || wb_trap));
    wire fetch_allowed=!halted && !serialize_pending && !irq_stop;
    assign frontend_starved=!reset && !halted && state==EMPTY && !fe_valid && !serialize_pending && !irq_stop;
    assign tlb_enabled=TLB_ENABLE!=0;
    assign tlb_invalidate_event=retire && (wb_sfence || (wb_csr && wb_insn[31:20]==12'h180));
    assign ras_enabled=RAS_ENABLE!=0 && PREDICT_ENABLE!=0;
    assign ras_prediction_event=control_resolve_event && ex_predicted_return;
    assign ras_miss_event=control_miss_event && ex_predicted_return;
    assign btb_enabled=BTB_ENABLE!=0 && PREDICT_ENABLE!=0;
    assign btb_train_event=btb_enabled && retire && (wb_insn[6:0]==7'h63 || wb_insn[6:0]==7'h6f || wb_insn[6:0]==7'h67);
    assign btb_prediction_event=control_resolve_event && ex_predicted_btb;
    assign btb_miss_event=control_miss_event && ex_predicted_btb;
    assign gshare_enabled=GSHARE_ENABLE!=0 && BHT_ENABLE!=0 && PREDICT_ENABLE!=0;
    assign bht_enabled=BHT_ENABLE!=0 && PREDICT_ENABLE!=0;
    assign bht_train_event=bht_enabled && retire && wb_insn[6:0]==7'h63;
    assign bht_taken_event=bht_train_event && wb_branch_taken;
    assign bht_prediction_event=conditional_resolve_event && ex_predicted_dynamic;
    assign bht_miss_event=control_miss_event && ex_predicted_dynamic;
    assign predictor_enabled=PREDICT_ENABLE!=0;
    assign split_memory_enabled=SPLIT_MEMORY!=0;
    assign icache_hit_during_data_fill=icache_hit_event && dcache_miss_wait;
    assign dcache_hit_during_instruction_fill=dcache_hit_event && icache_miss_wait;
    assign dcache_enabled=DCACHE_ENABLE!=0;
    assign icache_enabled=ICACHE_ENABLE!=0;
    assign fetch_buffer_enabled=FETCH_BUFFER_ENABLE!=0;
    assign icache_invalidate_event=retire && wb_insn[6:0]==7'h0f && wb_insn[14:12]==1;
    assign f_ready=arb_f_ready && fetch_allowed;
    assign extended_mode=EXTENSIONS!=0;
    assign host_traps_enabled=HOST_TRAPS!=0;
    assign current_privilege=privilege;

    reg ex_trap;
    reg [2:0] ex_fault;
    reg [63:0] ex_cause,ex_value;
    wire ex_done=(state==EXEC && (ex_trap || (!memory_op && !muldiv_op))) ||
        (state==DATA_RSP && d_rsp_valid) || (state==MD_WAIT && md_done);
    wire ex_finish=!reset && !halted && ex_done && (!wb_valid || wb_fire) && !wb_redirect;
    wire memory_finish=state==DATA_RSP;
    wire sc=mem_atomic && mem_amo==3;
    wire sc_success=sc && v_rsp_data==0;
    wire [63:0] load_result,raw_value,store_value,amo_new_value;
    wire [63:0] ex_result=memory_finish ? (sc ? v_rsp_data : load_result) : state==MD_WAIT ? md_result : decoded_result;
    wire [4:0] ex_rd=memory_finish ? mem_rd : rd;
    wire ex_rd_wen=!ex_trap && (memory_finish ? (!mem_write || mem_atomic) : write_rd) && ex_rd!=0;
    wire [63:0] ex_next=memory_finish || state==MD_WAIT ? pc+{61'd0,instruction_bytes} : effective_next;
    wire [63:0] retired_mem_data=mem_atomic ? (sc ? (sc_success ? store_value : 64'd0) : mem_amo==2 ? raw_value : amo_new_value) : mem_write ? store_value : raw_value;
    wire ex_redirect=ex_finish && !ex_trap && !ex_serial && ex_next!=ex_predicted_next;
    assign control_resolve_event=ex_finish && state==EXEC && !ex_trap &&
        (insn[6:0]==7'h63 || insn[6:0]==7'h6f || insn[6:0]==7'h67);
    assign conditional_resolve_event=control_resolve_event && insn[6:0]==7'h63;
    assign direct_jump_resolve_event=control_resolve_event && insn[6:0]==7'h6f;
    assign indirect_jump_resolve_event=control_resolve_event && insn[6:0]==7'h67;
    assign control_miss_event=control_resolve_event && ex_redirect;
    assign predicted_redirect_event=control_resolve_event && ex_predicted_next!=pc+{61'd0,instruction_bytes};
    wire redirect=wb_redirect || interrupt_take || ex_redirect;
    wire [63:0] redirect_pc=(trap_enter ? trap_vector : wb_redirect ? wb_next : ex_next);

    wire fe_serial=fe_insn[6:0]==7'h73 || fe_insn[6:0]==7'h0f;
    // Serial instructions enter X only after older X has vacated; older W may retire here.
    wire issue_fire=!reset && !halted && fe_valid && (state==EMPTY || ex_finish) &&
        !redirect && !serialize_pending && !irq_stop && !(ex_finish && (ex_trap || ex_serial)) &&
        (!fe_serial || state==EMPTY);
    assign fe_ready=issue_fire;
    assign dual_issue_enabled=DUAL_ISSUE!=0 && PAIR_ENABLE!=0;
    assign issue_lookahead_enabled=DUAL_ISSUE!=0;
    function automatic simple_pair_op(input [31:0] i);
      reg unused_fields;
      begin unused_fields=^{i[24:15],i[11:7]}; simple_pair_op=(i[6:0]==7'h13 && i[14:12]==0) ||
        (i[6:0]==7'h33 && i[14:12]==0 && (i[31:25]==0 || i[31:25]==7'h20));end
    endfunction
    wire [332:0] second_packet;wire second_valid;
    wire [63:0] p2_pc=second_packet[332:269],p2_next=second_packet[268:205];
    wire [31:0] p2_insn=second_packet[76:45],p2_raw=second_packet[44:13];
    wire [2:0] p2_bytes=second_packet[12:10];
    wire [4:0] p2_rs1=p2_insn[19:15],p2_rs2=p2_insn[24:20],p1_rd=fe_insn[11:7];
    wire p2_uses_rs2=p2_insn[6:0]==7'h33;
    wire pair_raw=p1_rd!=0 && (p1_rd==p2_rs1 || (p2_uses_rs2 && p1_rd==p2_rs2));
    wire pair_waw=p1_rd!=0 && p1_rd==p2_insn[11:7];
    wire pair_fire=DUAL_ISSUE!=0 && PAIR_ENABLE!=0 && issue_fire && second_valid && !fe_illegal && !fe_fault &&
      !second_packet[9] && !second_packet[8] && simple_pair_op(fe_insn) && simple_pair_op(p2_insn) && !pair_raw && !pair_waw &&
      fe_predicted_next==fe_pc+{61'd0,fe_bytes} && p2_pc==fe_predicted_next && p2_next==p2_pc+{61'd0,p2_bytes};
    wire unused_pair_metadata=^{second_packet[204:77],second_packet[7:0],xp_insn[29:25],xp_insn[19:12]};
    wire [63:0] register_c,register_d;
    function automatic [63:0] forwarded(input [4:0] r,input [63:0] rf);
      begin forwarded=r==0 ? 64'd0 : ex_finish && xp_valid && xp_rd==r ? xp_result :
        ex_finish && ex_rd_wen && ex_rd==r ? ex_result : retire && wb_pair && wp_rd==r ? wp_result :
        wb_write_enable && wb_rd==r ? wb_writeback : rf;end
    endfunction
    wire [4:0] issue_rs1=fe_insn[19:15],issue_rs2=fe_insn[24:20];
    wire [63:0] register_a,register_b;
    wire bypass_x_a=ex_finish && ex_rd_wen && ex_rd==issue_rs1 && issue_rs1!=0;
    wire bypass_x_b=ex_finish && ex_rd_wen && ex_rd==issue_rs2 && issue_rs2!=0;
    wire bypass_w_a=wb_write_enable && wb_rd==issue_rs1 && issue_rs1!=0;
    wire bypass_w_b=wb_write_enable && wb_rd==issue_rs2 && issue_rs2!=0;
    wire [63:0] issue_a=forwarded(issue_rs1,register_a);
    wire [63:0] issue_b=forwarded(issue_rs2,register_b);

    rv64_regfile registers(.clk(clk),.reset(reset),.write_enable(wb_write_enable),
        .rs1(issue_rs1),.rs2(issue_rs2),.rd(wb_rd),.write_data(wb_writeback),
        .rs3(p2_rs1),.rs4(p2_rs2),.rd2(wp_rd),.write2_enable(retire && wb_pair),.write2_data(wp_result),
        .a(register_a),.b(register_b),.c(register_c),.d(register_d),.debug_t3(debug_t3));
    rv64_alu alu(.insn(insn),.a(a),.b(b),.imm_i(imm_i),.legal(alu_legal),.result(alu_result));
    rv64_decoder #(.EXTENSIONS(EXTENSIONS)) decoder(.insn(insn),.pc(pc),.a(a),.b(b),.alu_result(alu_result),
        .instruction_bytes(instruction_bytes),.alu_legal(alu_legal),.rd(rd),.rs1(rs1),.rs2(rs2),.imm_i(imm_i),.address(address),
        .legal(legal),.write_rd(write_rd),.memory_op(memory_op),.csr_op(csr_op),.muldiv_op(muldiv_op),.atomic_op(atomic_op),
        .ecall(ecall),.ebreak_op(ebreak_op),.mret(mret),.sret(sret),.wfi(wfi),.sfence(sfence),
        .branch_taken(decoded_branch_taken),.result(decoded_result),.next_pc(decoded_next));
    rv64_lsu lsu(.raw_data(v_rsp_data),.store_data(mem_wdata),.size(mem_size),.unsigned_load(mem_unsigned),
        .load_result(load_result),.raw_value(raw_value),.store_value(store_value));
    rv64_amo_alu commit_atomic(.old_value(v_rsp_data),.operand(mem_wdata),.word_op(mem_size==2),.operation(mem_amo),.new_value(amo_new_value));
    rv64_muldiv muldiv(.clk(clk),.reset(reset),.start(state==EXEC && muldiv_op && !ex_trap && !md_busy),
        .word_op(insn[6:0]==7'h3b),.operation(insn[14:12]),.a(a),.b(b),.busy(md_busy),.done(md_done),.result(md_result));
    wire csr_w_stage=wb_valid && wb_serial;
    wire [31:0] csr_insn=csr_w_stage ? wb_insn : insn;
    rv64_csr #(.EXTENSIONS(EXTENSIONS)) csrs(.clk(clk),.reset(reset),.retire(retire),.retire_extra(wb_pair && retire),.irq_pending(irq_pending),.time_value(time_value),
        .csr_request(csr_w_stage ? wb_csr : csr_op),.csr_commit(retire && wb_csr),
        .address(csr_insn[31:20]),.command(csr_insn[14:12]),.source_index(csr_insn[19:15]),.source_value(csr_w_stage ? wb_source : a),
        .read_data(csr_read),.illegal(csr_illegal),.mret(csr_w_stage ? wb_mret : mret),.sret(csr_w_stage ? wb_sret : sret),
        .wfi(csr_w_stage ? wb_insn==32'h10500073 : wfi),.sfence(csr_w_stage ? wb_sfence : sfence),
        .return_commit(retire && (wb_mret || wb_sret)),.system_illegal(system_illegal),.return_pc(return_pc),
        .trap(trap_enter && EXTENSIONS!=0 && HOST_TRAPS==0),.exception_pc(trap_exception_pc),
        .exception_cause(trap_exception_cause),.exception_value(trap_exception_value),
        .vector(trap_vector),.privilege(privilege),.data_privilege(data_privilege),.satp(satp),.sum(sum),.mxr(mxr),
        .interrupt_valid(interrupt_valid),.interrupt_cause(interrupt_cause));

    wire ras_valid;
    wire [63:0] ras_target;
    wire [3:0] unused_ras_occupancy;
    // Conservatively discard history at all serial commits and trap/interrupt entry.
    rv64_return_stack #(.ENABLED(RAS_ENABLE!=0 && PREDICT_ENABLE!=0)) return_stack(
        .clk(clk),.reset(reset),.clear(trap_enter || (retire && wb_serial)),.retire(retire),
        .insn(wb_insn),.pc(wb_pc),.bytes(wb_bytes),.valid(ras_valid),.target(ras_target),
        .push_event(ras_push_event),.pop_event(ras_pop_event),.overflow_event(ras_overflow_event),.underflow_event(ras_underflow_event),.occupancy(unused_ras_occupancy));
    wire raw_fe_valid,raw_fe_ready,raw_fe_illegal,raw_fe_fault,raw_fe_active,raw_fe_predicted_return,raw_fe_predicted_dynamic,raw_fe_predicted_btb;
    wire [63:0] raw_fe_pc,raw_fe_cause,raw_fe_value,raw_fe_predicted_next;
    wire [31:0] raw_fe_insn,raw_fe_raw;
    wire [2:0] raw_fe_bytes;
    wire [4:0] raw_fe_predicted_index;
    wire [332:0] raw_fe_packet={raw_fe_pc,raw_fe_predicted_next,raw_fe_cause,raw_fe_value,
        raw_fe_insn,raw_fe_raw,raw_fe_bytes,raw_fe_illegal,raw_fe_fault,raw_fe_predicted_return,
        raw_fe_predicted_dynamic,raw_fe_predicted_btb,raw_fe_predicted_index};
    wire [332:0] fe_packet,queued_packet;wire queued_valid,queued_ready;
    assign {fe_pc,fe_predicted_next,fe_cause,fe_value,fe_insn,fe_raw,fe_bytes,fe_illegal,fe_fault,
        fe_predicted_return,fe_predicted_dynamic,fe_predicted_btb,fe_predicted_index}=fe_packet;
    assign fe_active=raw_fe_active || fetch_queue_occupancy!=0 || issue_pair_occupancy!=0;
    assign fetch_queue_fill_while_x_busy=fetch_queue_push_event && state!=EMPTY && !ex_finish;
    assign fetch_queue_enabled=FETCH_QUEUE_ENABLE!=0;
    wire fetch_redirect=redirect || (I_PIPELINE!=0 && (irq_stop || (ex_finish && (ex_trap || ex_serial))));
    wire [63:0] fetch_redirect_pc=redirect ? redirect_pc : irq_stop ? architectural_pc : ex_next;
    rv64_fetch_queue #(.ENABLED(FETCH_QUEUE_ENABLE)) instruction_queue(
        .clk(clk),.reset(reset),.flush(fetch_redirect),.u_valid(raw_fe_valid),.u_ready(raw_fe_ready),.u_packet(raw_fe_packet),
        .d_valid(queued_valid),.d_ready(queued_ready),.d_packet(queued_packet),.occupancy(fetch_queue_occupancy),
        .push_event(fetch_queue_push_event),.pop_event(fetch_queue_pop_event),.bypass_event(fetch_queue_bypass_event),
        .full_stall(fetch_queue_full_stall),.flush_event(fetch_queue_flush_event));
    rv64_issue_pair_queue #(.ENABLED(DUAL_ISSUE)) issue_pairs(
      .clk(clk),.reset(reset),.flush(fetch_redirect),.u_valid(queued_valid),.u_ready(queued_ready),.u_packet(queued_packet),
      .d_valid(fe_valid),.second_valid(second_valid),.pop_count(fe_ready ? (pair_fire ? 2'd2 : 2'd1) : 2'd0),
      .d_packet(fe_packet),.second_packet(second_packet),.occupancy(issue_pair_occupancy));
    rv64_fetch #(.EXTENSIONS(EXTENSIONS),.BUFFER_ENABLE(FETCH_BUFFER_ENABLE),.PREDICT_ENABLE(PREDICT_ENABLE),.RAS_ENABLE(RAS_ENABLE),.BHT_ENABLE(BHT_ENABLE),.GSHARE_ENABLE(GSHARE_ENABLE),.BTB_ENABLE(BTB_ENABLE),.I_PIPELINE(I_PIPELINE!=0 && SPLIT_MEMORY!=0)) frontend(.clk(clk),.reset(reset),.redirect(fetch_redirect),.redirect_pc(fetch_redirect_pc),.ras_valid(ras_valid),.ras_target(ras_target),
        .btb_train(btb_train_event),.btb_train_pc(wb_pc),.btb_train_insn(wb_insn),.btb_train_bytes(wb_bytes),.btb_train_next(wb_next),
        .btb_lookup_pc(unused_fe_query_pc),.predicted_btb(raw_fe_predicted_btb),.btb_lookup_event(btb_lookup_event),.btb_hit_event(btb_hit_event),.btb_reject_event(btb_reject_event),
        .bht_clear(trap_enter || (retire && wb_serial)),.bht_train(bht_train_event),
        .bht_train_index(wb_predicted_index),.predicted_index(raw_fe_predicted_index),.global_history(global_history),
        .bht_train_pc(wb_pc),.bht_train_taken(wb_branch_taken),.predicted_dynamic(raw_fe_predicted_dynamic),
        .req_valid(f_valid),.req_ready(f_ready),.req_addr(f_addr),.req_size(f_size),
        .rsp_valid(f_rsp_valid),.rsp_ready(f_rsp_ready),.rsp_data(f_rsp_data),.rsp_cause(f_rsp_cause),.rsp_error(f_rsp_error),
        .valid(raw_fe_valid),.ready(raw_fe_ready),.pc(raw_fe_pc),.predicted_next(raw_fe_predicted_next),.predicted_return(raw_fe_predicted_return),.fault_cause(raw_fe_cause),.fault_value(raw_fe_value),
        .insn(raw_fe_insn),.raw_insn(raw_fe_raw),.bytes(raw_fe_bytes),.illegal(raw_fe_illegal),.fetch_fault(raw_fe_fault),.waiting(fe_waiting),.active(raw_fe_active),
        .discard_event(fetch_discard_event),.reuse_event(fetch_buffer_reuse_event),.buffer_flush_event(fetch_buffer_flush_event));
    assign icache_fill_forward_enabled=ICACHE_FILL_FORWARD!=0 && ICACHE_ENABLE!=0 && EARLY_RESTART!=0 && I_PIPELINE!=0 && SPLIT_MEMORY!=0;
    assign icache_refill_hits_enabled=ICACHE_HIT_UNDER_REFILL!=0 && ICACHE_ENABLE!=0 && EARLY_RESTART!=0 && I_PIPELINE!=0 && SPLIT_MEMORY!=0;
    assign demand_priority_enabled=DEMAND_PRIORITY!=0 && FETCH_WINDOW!=0;
    assign demand_issue_enabled=DEMAND_ISSUE!=0 && FETCH_WINDOW!=0;
    assign window_forward_enabled=WINDOW_FORWARD!=0 && FETCH_WINDOW!=0;
    assign prefetch_path_enabled=PREFETCH_PATH!=0 && FETCH_WINDOW!=0 && PREDICT_ENABLE!=0 && BTB_ENABLE!=0;
    assign ifetch_window_enabled=FETCH_WINDOW!=0;
    assign bus_busy=raw_bus_busy || window_busy;
    rv64_fetch_window #(.ENABLED(FETCH_WINDOW),.DEMAND_PRIORITY(DEMAND_PRIORITY),.DEMAND_ISSUE(DEMAND_ISSUE),.WINDOW_FORWARD(WINDOW_FORWARD),.PREFETCH_PATH(PREFETCH_PATH),.EXTENSIONS(EXTENSIONS),
        .BTB_ENABLE(BTB_ENABLE),.BHT_ENABLE(BHT_ENABLE),.GSHARE_ENABLE(GSHARE_ENABLE),.PREDICT_ENABLE(PREDICT_ENABLE)) request_window(
        .clk(clk),.reset(reset),.flush(fetch_redirect),.allow(fetch_allowed),
        .predictor_clear(trap_enter || (retire && wb_serial)),.btb_train(btb_train_event),.train_pc(wb_pc),.train_insn(wb_insn),.train_next(wb_next),.train_bytes(wb_bytes),
        .bht_train(bht_train_event),.train_taken(wb_branch_taken),.train_index(wb_predicted_index),.ras_valid(ras_valid),.ras_target(ras_target),
        .path_query_event(prefetch_path_query_event),.path_redirect_event(prefetch_path_redirect_event),.path_reject_event(prefetch_path_reject_event),.path_page_block_event(prefetch_path_page_block_event),
        .u_valid(f_valid && fetch_allowed),.u_ready(arb_f_ready),.u_addr(f_addr),.u_size(f_size),
        .u_rsp_valid(f_rsp_valid),.u_rsp_ready(f_rsp_ready),.u_rsp_data(f_rsp_data),.u_rsp_cause(f_rsp_cause),.u_rsp_error(f_rsp_error),
        .d_valid(mw_valid),.d_ready(mw_ready),.d_addr(mw_addr),.d_size(mw_size),
        .d_rsp_valid(mw_rsp_valid),.d_rsp_ready(mw_rsp_ready),.d_rsp_data(mw_rsp_data),.d_rsp_cause(mw_rsp_cause),.d_rsp_error(mw_rsp_error),
        .busy(window_busy),.pending(ifetch_window_pending),.hit_event(ifetch_window_hit_event),.drop_event(ifetch_window_drop_event));
    rv64_ifetch_response_pipe #(.ENABLED(FETCH_WINDOW)) instruction_response_stage(
        .clk(clk),.reset(reset),.u_valid(mi_rsp_valid),.u_ready(mi_rsp_ready),.u_packet({mi_rsp_error,mi_rsp_cause,mi_rsp_data}),
        .d_valid(mw_rsp_valid),.d_ready(mw_rsp_ready),.d_packet({mw_rsp_error,mw_rsp_cause,mw_rsp_data}));
    rv64_memory_system #(.SPLIT_MEMORY(SPLIT_MEMORY),.ICACHE_ENABLE(ICACHE_ENABLE),.FETCH_BUFFER_ENABLE(FETCH_BUFFER_ENABLE),
        .EARLY_RESTART(EARLY_RESTART),.DCACHE_ENABLE(DCACHE_ENABLE),.DCACHE_EARLY_RESTART(DCACHE_EARLY_RESTART),.TLB_ENABLE(TLB_ENABLE),.I_PIPELINE(I_PIPELINE),.ICACHE_HIT_UNDER_REFILL(ICACHE_HIT_UNDER_REFILL),.ICACHE_FILL_FORWARD(ICACHE_FILL_FORWARD)) memory_system(
        .clk(clk),.reset(reset),.clear_reservation(reservation_invalidate || trap_enter || (retire && (wb_mret || wb_sret || wb_sfence))),
        .reservation_invalidate(reservation_invalidate),.icache_invalidate(icache_invalidate_event),.tlb_invalidate(tlb_invalidate_event),
        .privilege(privilege),.data_privilege(data_privilege),.satp(satp),.sum(sum),.mxr(mxr),
        .f_valid(mw_valid),.f_ready(mw_ready),.f_addr(mw_addr),.f_size(mw_size),
        .f_rsp_valid(mi_rsp_valid),.f_rsp_ready(mi_rsp_ready),.f_rsp_data(mi_rsp_data),.f_rsp_cause(mi_rsp_cause),.f_rsp_error(mi_rsp_error),
        .d_valid(!reset && !halted && state==DATA_REQ),.d_ready(d_ready),.d_addr(mem_addr),.d_data(mem_wdata),
        .d_size(mem_size),.d_write(mem_write),.d_atomic(mem_atomic),.d_amo(mem_amo),
        .d_rsp_valid(d_rsp_valid),.d_rsp_ready(data_rsp_ready),.d_rsp_data(v_rsp_data),.d_rsp_cause(v_rsp_cause),.d_rsp_error(v_rsp_error),
        .req_valid(req_valid),.req_ready(req_ready),.req_addr(req_addr),.req_wdata(req_wdata),.req_size(req_size),.req_write(req_write),.req_store_check(req_store_check),
        .rsp_valid(rsp_valid),.rsp_ready(rsp_ready),.rsp_rdata(rsp_rdata),.rsp_error(rsp_error),.bus_lock(bus_lock),.busy(raw_bus_busy),
        .icache_fill_hit_event(icache_fill_hit_event),.icache_refill_hit_event(icache_refill_hit_event),.icache_hit_event(icache_hit_event),.icache_miss_event(icache_miss_event),.icache_refill_event(icache_refill_event),.icache_miss_wait(icache_miss_wait),.icache_bypass_event(icache_bypass_event),
        .dcache_hit_event(dcache_hit_event),.dcache_miss_event(dcache_miss_event),.dcache_refill_event(dcache_refill_event),.dcache_miss_wait(dcache_miss_wait),.dcache_write_event(dcache_write_event),.dcache_bypass_event(dcache_bypass_event),
        .itlb_hit_event(itlb_hit_event),.itlb_miss_event(itlb_miss_event),.itlb_fill_event(itlb_fill_event),
        .dtlb_hit_event(dtlb_hit_event),.dtlb_miss_event(dtlb_miss_event),.dtlb_fill_event(dtlb_fill_event),.i_walk_event(i_walk_event),.d_walk_event(d_walk_event),
        .data_blocked_by_fetch(data_blocked_by_fetch),.fetch_blocked_by_data(fetch_blocked_by_data));

    always @* begin
        ex_trap=0; ex_fault=0; ex_cause=0; ex_value=0;
        if (state==EXEC) begin
            if (fetch_fault) begin ex_trap=1; ex_fault=3; ex_cause=fetch_cause; ex_value=fetch_value; end
            else if (!legal || compressed_illegal || csr_illegal || system_illegal) begin
                ex_trap=1; ex_fault=1; ex_cause=2; ex_value={32'd0,raw_insn};
            end else if (ecall || ebreak_op) begin
                ex_trap=1; ex_fault=ecall ? 3'd4 : 3'd5;
                ex_cause=ebreak_op ? 64'd3 : privilege==3 ? 64'd11 : privilege==1 ? 64'd9 : 64'd8;
            end else if (EXTENSIONS!=0 ? effective_next[0] : |effective_next[1:0]) begin
                ex_trap=1; ex_fault=2; ex_value=effective_next;
            end else if (memory_op && (address & alignment_mask)!=0) begin
                ex_trap=1; ex_fault=2; ex_cause=decoded_write ? 64'd6 : 64'd4; ex_value=address;
            end
        end else if (state==DATA_RSP && d_rsp_valid && v_rsp_error) begin
            ex_trap=1; ex_fault=3; ex_cause=v_rsp_cause; ex_value=mem_addr;
        end
    end

    always @(posedge clk) begin
        if (reset) begin
            ex_predicted_btb<=0; ex_predicted_index<=0; wb_predicted_index<=0;
            wb_branch_taken<=0; ex_predicted_dynamic<=0;
            xp_valid<=0;wb_pair<=0;xp_pc<=0;xp_a<=0;xp_b<=0;xp_insn<=0;xp_raw<=0;xp_bytes<=4;
            wp_pc<=0;wp_next<=0;wp_result<=0;wp_raw<=0;wp_bytes<=4;wp_rd<=0;
            commit2_valid<=0;commit2_pc<=0;commit2_next_pc<=0;commit2_wdata<=0;commit2_insn<=0;
            commit2_rd<=0;commit2_rd_wen<=0;commit2_bytes<=4;commit2_privilege<=3;dual_issue_pairs<=0;
            state<=EMPTY; architectural_pc<=0; pc<=0; ex_predicted_next<=0; ex_predicted_return<=0; a<=0; b<=0; insn<=0; raw_insn<=0;
            instruction_bytes<=4; compressed_illegal<=0; fetch_fault<=0; fetch_cause<=0; fetch_value<=0;
            mem_addr<=0; mem_wdata<=0; mem_write<=0; mem_unsigned<=0; mem_atomic<=0; mem_rd<=0; mem_size<=0; mem_amo<=0;
            wb_valid<=0; wb_trap<=0; wb_serial<=0; wb_csr<=0; wb_mret<=0; wb_sret<=0; wb_sfence<=0;
            wb_fault<=0; wb_bytes<=4; wb_pc<=0; wb_next<=0; wb_result<=0; wb_source<=0; wb_cause<=0; wb_value<=0;
            wb_insn<=0; wb_raw<=0; wb_privilege<=3; wb_rd_wen<=0; wb_rd<=0;
            wb_mem_valid<=0; wb_mem_write<=0; wb_mem_atomic<=0; wb_amo<=0; wb_size<=0; wb_mem_addr<=0; wb_mem_data<=0;
            halted<=0; fault<=0; trap_valid<=0; trap_pc<=0; trap_cause<=0; trap_value<=0; trap_target<=0;
            cycles<=0; instret<=0; fetch_wait<=0; data_wait<=0;
            commit_valid<=0; commit_pc<=0; commit_insn<=0; commit_bytes<=4; commit_privilege<=3;
            commit_rd_wen<=0; commit_rd<=0; commit_wdata<=0; commit_next_pc<=0;
            commit_mem_valid<=0; commit_mem_write<=0; commit_mem_addr<=0; commit_mem_data<=0;
            commit_mem_size<=0; commit_mem_atomic<=0; commit_mem_amo<=0;
            overlap_cycles<=0; xw_overlap_cycles<=0; issue_count<=0; bypass_count<=0; flush_count<=0;
        end else begin
            commit_valid<=0;commit2_valid<=0; trap_valid<=0;
            commit_rd_wen<=0; commit_rd<=0; commit_wdata<=0;
            commit_mem_valid<=0; commit_mem_write<=0; commit_mem_addr<=0; commit_mem_data<=0;
            commit_mem_size<=0; commit_mem_atomic<=0; commit_mem_amo<=0;
            if (!halted) begin
                cycles<=cycles+1;
                if (fe_waiting) fetch_wait<=fetch_wait+1;
                if (state==DATA_RSP && !d_rsp_valid) data_wait<=data_wait+1;
                if ((state!=EMPTY && (wb_valid || fe_active)) || (wb_valid && fe_active)) overlap_cycles<=overlap_cycles+1;
                if (state!=EMPTY && wb_valid) xw_overlap_cycles<=xw_overlap_cycles+1;
                if (redirect) flush_count<=flush_count+1;
            end
            if (wb_fire) begin
                wb_valid<=0;wb_pair<=0;
                if (!wb_trap) begin
                    commit_valid<=1; commit_pc<=wb_pc; commit_insn<=wb_raw; commit_next_pc<=wb_next;
                    commit_bytes<=wb_bytes; commit_privilege<=wb_privilege;
                    commit_rd_wen<=wb_write_enable; commit_rd<=wb_write_enable ? wb_rd : 5'd0;
                    commit_wdata<=wb_write_enable ? wb_writeback : 64'd0;
                    commit_mem_valid<=wb_mem_valid; commit_mem_write<=wb_mem_write;
                    commit_mem_addr<=wb_mem_addr; commit_mem_data<=wb_mem_data; commit_mem_size<=wb_size;
                    commit_mem_atomic<=wb_mem_atomic; commit_mem_amo<=wb_amo;
                    instret<=instret+1+{63'd0,wb_pair}; architectural_pc<=wb_pair ? wp_next : wb_next;
                    if(wb_pair)begin
                      commit2_valid<=1;commit2_pc<=wp_pc;commit2_next_pc<=wp_next;commit2_insn<=wp_raw;
                      commit2_rd_wen<=wp_rd!=0;commit2_rd<=wp_rd;commit2_wdata<=wp_rd!=0 ? wp_result : 64'd0;
                      commit2_bytes<=wp_bytes;commit2_privilege<=wb_privilege;
                    end
                end
            end
            if (trap_enter) begin
                trap_valid<=1; trap_pc<=trap_exception_pc; trap_cause<=trap_exception_cause;
                trap_value<=trap_exception_value; trap_target<=trap_vector;
                architectural_pc<=trap_vector;
                if (HOST_TRAPS!=0) begin halted<=1; fault<=wb_fault; end
            end
            if (wb_redirect || interrupt_take) begin state<=EMPTY; wb_valid<=0;xp_valid<=0; end
            else if (!halted) begin
                if (ex_finish) begin
                    xp_valid<=0;wb_pair<=xp_valid && !ex_trap;
                    wp_pc<=xp_pc;wp_next<=xp_pc+{61'd0,xp_bytes};wp_result<=xp_result;wp_raw<=xp_raw;wp_bytes<=xp_bytes;wp_rd<=xp_rd;
                    state<=EMPTY; wb_valid<=1; wb_trap<=ex_trap; wb_fault<=ex_fault;
                    wb_serial<=ex_serial; wb_csr<=csr_op; wb_mret<=mret; wb_sret<=sret; wb_sfence<=sfence;
                    wb_predicted_index<=ex_predicted_index;
                    wb_branch_taken<=decoded_branch_taken;
                    wb_pc<=pc; wb_next<=ex_next; wb_result<=ex_result; wb_source<=a;
                    wb_cause<=ex_cause; wb_value<=ex_value; wb_insn<=insn; wb_raw<=raw_insn;
                    wb_bytes<=instruction_bytes; wb_privilege<=privilege; wb_rd_wen<=ex_rd_wen; wb_rd<=ex_rd;
                    wb_mem_valid<=memory_finish && !ex_trap;
                    wb_mem_write<=memory_finish && !ex_trap && mem_write && (!sc || sc_success);
                    wb_mem_atomic<=memory_finish && !ex_trap && mem_atomic;
                    wb_amo<=memory_finish && mem_atomic ? mem_amo : 5'd0;
                    wb_mem_addr<=memory_finish ? mem_addr : 64'd0;
                    wb_mem_data<=memory_finish ? retired_mem_data : 64'd0;
                    wb_size<=memory_finish ? mem_size : 2'd0;
                end else case (state)
                    EXEC: if (!ex_trap) begin
                        if (memory_op) begin
                            mem_addr<=address; mem_wdata<=b; mem_rd<=rd; mem_size<=insn[13:12];
                            mem_write<=decoded_write; mem_unsigned<=!atomic_op && insn[14];
                            mem_atomic<=atomic_op; mem_amo<=insn[31:27]; state<=DATA_REQ;
                        end else if (muldiv_op) state<=MD_WAIT;
                    end
                    DATA_REQ: if (d_ready) state<=DATA_RSP;
                    default: ;
                endcase
                if (issue_fire) begin
                    state<=EXEC; pc<=fe_pc; insn<=fe_insn; raw_insn<=fe_raw; instruction_bytes<=fe_bytes; ex_predicted_next<=fe_predicted_next; ex_predicted_return<=fe_predicted_return; ex_predicted_dynamic<=fe_predicted_dynamic; ex_predicted_index<=fe_predicted_index; ex_predicted_btb<=fe_predicted_btb;
                    a<=issue_a; b<=issue_b; compressed_illegal<=fe_illegal;
                    fetch_fault<=fe_fault; fetch_cause<=fe_cause; fetch_value<=fe_value;
                    xp_valid<=pair_fire;xp_pc<=p2_pc;xp_a<=forwarded(p2_rs1,register_c);xp_b<=forwarded(p2_rs2,register_d);xp_insn<=p2_insn;xp_raw<=p2_raw;xp_bytes<=p2_bytes;
                    issue_count<=issue_count+1+{63'd0,pair_fire};
                    if(pair_fire)dual_issue_pairs<=dual_issue_pairs+1;
                    if (bypass_x_a || bypass_x_b || bypass_w_a || bypass_w_b) bypass_count<=bypass_count+1;
                end
            end
        end
    end
    wire unused_rs_fields=^{rs1,rs2,csr_insn[11:0]};
endmodule
