// Separate translation/cache paths; a compile-time legacy path supports controlled comparison.
module rv64_memory_system #(parameter SPLIT_MEMORY=1, ICACHE_ENABLE=1, FETCH_BUFFER_ENABLE=1,
    EARLY_RESTART=1, DCACHE_ENABLE=1, DCACHE_EARLY_RESTART=1, TLB_ENABLE=1, I_PIPELINE=0, ICACHE_HIT_UNDER_REFILL=1, ICACHE_FILL_FORWARD=1, ICACHE_WIDE_READ=0, DATA_REFILL_FORWARD=0) (
    input wire clk,reset,clear_reservation,reservation_invalidate,icache_invalidate,tlb_invalidate,
    input wire [1:0] privilege,data_privilege,input wire [63:0] satp,input wire sum,mxr,
    input wire f_valid,output wire f_ready,input wire [63:0] f_addr,input wire [1:0] f_size,
    output wire f_rsp_valid,input wire f_rsp_ready,output wire [63:0] f_rsp_data,f_rsp_cause,output wire f_rsp_error,
    input wire d_valid,output wire d_ready,input wire [63:0] d_addr,d_data,input wire [1:0] d_size,
    input wire d_write,d_atomic,input wire [4:0] d_amo,
    output wire d_rsp_valid,input wire d_rsp_ready,output wire [63:0] d_rsp_data,d_rsp_cause,output wire d_rsp_error,
    output wire req_valid,input wire req_ready,output wire [63:0] req_addr,req_wdata,
    output wire [1:0] req_size,output wire req_write,req_store_check,
    input wire rsp_valid,output wire rsp_ready,input wire [63:0] rsp_rdata,input wire rsp_error,
    output wire bus_lock,busy,
    output wire icache_fill_hit_event,icache_refill_hit_event,icache_hit_event,icache_miss_event,icache_refill_event,icache_miss_wait,icache_bypass_event,
    output wire dcache_hit_event,dcache_miss_event,dcache_refill_event,dcache_miss_wait,dcache_write_event,dcache_bypass_event,
    output wire itlb_hit_event,itlb_miss_event,itlb_fill_event,dtlb_hit_event,dtlb_miss_event,dtlb_fill_event,i_walk_event,d_walk_event,
    output wire data_blocked_by_fetch,fetch_blocked_by_data
);
    // The frontend buffer parameter is owned by the core, retained in this interface for snapshots.
    wire unused_buffer_parameter=FETCH_BUFFER_ENABLE!=0;
    generate if(SPLIT_MEMORY==0) begin: legacy
    wire [63:0] v_rsp_data,v_rsp_cause;
    wire v_rsp_error,unused_mmu_busy;
    wire v_valid,v_ready,v_write,v_execute,v_atomic,v_rsp_valid,v_rsp_ready;
    wire [63:0] v_addr,v_data;
    wire [1:0] v_size;
    wire [4:0] v_amo;
    rv64_bus_arbiter arbiter(.clk(clk),.reset(reset),.f_valid(f_valid),.f_ready(f_ready),.f_addr(f_addr),.f_size(f_size),
        .f_rsp_valid(f_rsp_valid),.f_rsp_ready(f_rsp_ready),
        .d_valid(d_valid),.d_ready(d_ready),.d_addr(d_addr),.d_data(d_data),
        .d_size(d_size),.d_write(d_write),.d_atomic(d_atomic),.d_amo(d_amo),
        .d_rsp_valid(d_rsp_valid),.d_rsp_ready(d_rsp_ready),
        .u_valid(v_valid),.u_ready(v_ready),.u_addr(v_addr),.u_data(v_data),.u_size(v_size),.u_write(v_write),.u_execute(v_execute),
        .u_atomic(v_atomic),.u_amo(v_amo),.u_rsp_valid(v_rsp_valid),.u_rsp_ready(v_rsp_ready),.busy(busy),
        .data_blocked_by_fetch(data_blocked_by_fetch),.fetch_blocked_by_data(fetch_blocked_by_data));
    wire p_valid,p_ready,p_write,p_atomic,p_execute,p_cache_data,p_rsp_valid,p_rsp_ready,p_rsp_error;
    wire [63:0] p_addr,p_data,p_rsp_data;
    wire [1:0] p_size;
    wire [4:0] p_amo;
    wire legacy_hit,legacy_miss,legacy_fill,legacy_walk;
    assign itlb_hit_event=legacy_hit && v_execute; assign dtlb_hit_event=legacy_hit && !v_execute;
    assign itlb_miss_event=legacy_miss && v_execute; assign dtlb_miss_event=legacy_miss && !v_execute;
    assign itlb_fill_event=legacy_fill && v_execute; assign dtlb_fill_event=legacy_fill && !v_execute;
    assign i_walk_event=legacy_walk && v_execute; assign d_walk_event=legacy_walk && !v_execute;
    rv64_mmu #(.TLB_ENABLE(TLB_ENABLE)) mmu(.clk(clk),.reset(reset),.privilege(privilege),.data_privilege(data_privilege),.satp(satp),.sum(sum),.mxr(mxr),.tlb_invalidate(tlb_invalidate),
        .u_valid(v_valid),.u_ready(v_ready),.u_addr(v_addr),.u_data(v_data),.u_size(v_size),.u_write(v_write),
        .u_execute(v_execute),.u_atomic(v_atomic),.u_amo(v_amo),
        .u_rsp_valid(v_rsp_valid),.u_rsp_ready(v_rsp_ready),.u_rsp_data(v_rsp_data),.u_rsp_error(v_rsp_error),.u_rsp_cause(v_rsp_cause),.busy(unused_mmu_busy),.tlb_hit_event(legacy_hit),.tlb_miss_event(legacy_miss),.tlb_fill_event(legacy_fill),.walk_event(legacy_walk),
        .d_valid(p_valid),.d_ready(p_ready),.d_addr(p_addr),.d_data(p_data),.d_size(p_size),.d_write(p_write),.d_atomic(p_atomic),.d_execute(p_execute),.d_cache_data(p_cache_data),.d_amo(p_amo),
        .d_rsp_valid(p_rsp_valid),.d_rsp_ready(p_rsp_ready),.d_rsp_data(p_rsp_data),.d_rsp_error(p_rsp_error));
    wire q_valid,q_ready,q_write,q_execute,q_atomic,q_rsp_valid,q_rsp_ready,q_rsp_error;
    wire [63:0] q_addr,q_data,q_rsp_data;
    wire [1:0] q_size;
    wire [4:0] q_amo;
    rv64_dcache #(.ENABLED(DCACHE_ENABLE),.EARLY_RESTART(DCACHE_EARLY_RESTART),.REFILL_FORWARD(DATA_REFILL_FORWARD)) dcache(.clk(clk),.reset(reset),.invalidate(reservation_invalidate),
        .u_valid(p_valid),.u_ready(p_ready),.u_addr(p_addr),.u_data(p_data),.u_size(p_size),.u_write(p_write),
        .u_execute(p_execute),.u_cache_data(p_cache_data),.u_atomic(p_atomic),.u_amo(p_amo),
        .u_rsp_valid(p_rsp_valid),.u_rsp_ready(p_rsp_ready),.u_rsp_data(p_rsp_data),.u_rsp_error(p_rsp_error),
        .d_valid(q_valid),.d_ready(q_ready),.d_addr(q_addr),.d_data(q_data),.d_size(q_size),.d_write(q_write),
        .d_execute(q_execute),.d_atomic(q_atomic),.d_amo(q_amo),
        .d_rsp_valid(q_rsp_valid),.d_rsp_ready(q_rsp_ready),.d_rsp_data(q_rsp_data),.d_rsp_error(q_rsp_error),
        .hit_event(dcache_hit_event),.miss_event(dcache_miss_event),.refill_event(dcache_refill_event),
        .miss_wait(dcache_miss_wait),.write_event(dcache_write_event),.bypass_event(dcache_bypass_event));
    wire c_valid,c_ready,c_write,c_atomic,c_rsp_valid,c_rsp_ready,c_rsp_error;
    wire [63:0] c_addr,c_data,c_rsp_data;
    wire [1:0] c_size;
    wire [4:0] c_amo;
    rv64_icache #(.ENABLED(ICACHE_ENABLE),.EARLY_RESTART(EARLY_RESTART)) icache(.clk(clk),.reset(reset),.invalidate(icache_invalidate),
        .u_valid(q_valid),.u_ready(q_ready),.u_addr(q_addr),.u_data(q_data),.u_size(q_size),.u_write(q_write),.u_execute(q_execute),
        .u_atomic(q_atomic),.u_amo(q_amo),.u_rsp_valid(q_rsp_valid),.u_rsp_ready(q_rsp_ready),.u_rsp_data(q_rsp_data),.u_rsp_error(q_rsp_error),
        .d_valid(c_valid),.d_ready(c_ready),.d_addr(c_addr),.d_data(c_data),.d_size(c_size),.d_write(c_write),.d_atomic(c_atomic),.d_amo(c_amo),
        .d_rsp_valid(c_rsp_valid),.d_rsp_ready(c_rsp_ready),.d_rsp_data(c_rsp_data),.d_rsp_error(c_rsp_error),
        .hit_event(icache_hit_event),.miss_event(icache_miss_event),.refill_event(icache_refill_event),.miss_wait(icache_miss_wait),
        .bypass_event(icache_bypass_event),.refill_hit_event(icache_refill_hit_event),.fill_hit_event(icache_fill_hit_event));
    rv64_atomic_adapter atomics(.clk(clk),.reset(reset),
        .clear_reservation(clear_reservation),
        .u_valid(c_valid),.u_ready(c_ready),.u_addr(c_addr),.u_data(c_data),.u_write(c_write),.u_atomic(c_atomic),.u_amo(c_amo),.u_size(c_size),
        .u_rsp_valid(c_rsp_valid),.u_rsp_ready(c_rsp_ready),.u_rsp_data(c_rsp_data),.u_rsp_error(c_rsp_error),
        .d_valid(req_valid),.d_ready(req_ready),.d_addr(req_addr),.d_data(req_wdata),.d_write(req_write),.d_store_check(req_store_check),.d_size(req_size),
        .d_rsp_valid(rsp_valid),.d_rsp_ready(rsp_ready),.d_rsp_data(rsp_rdata),.d_rsp_error(rsp_error),.bus_lock(bus_lock));
    assign f_rsp_data=v_rsp_data;
    assign f_rsp_cause=v_rsp_cause;
    assign f_rsp_error=v_rsp_error;
    assign d_rsp_data=v_rsp_data;
    assign d_rsp_cause=v_rsp_cause;
    assign d_rsp_error=v_rsp_error;
    end else begin: split
    wire ip_valid,ip_ready,ip_write,ip_atomic,ip_execute,ip_cache_data;
    wire [63:0] ip_addr,ip_data,ip_rsp_data;
    wire [1:0] ip_size;
    wire [4:0] ip_amo;
    wire ip_rsp_valid,ip_rsp_ready,ip_rsp_error,ip_busy;
    reg ip_cached;
    always @(posedge clk) begin
        if(reset) ip_cached<=0;
        else if(ip_valid && ip_ready) ip_cached<=ip_execute;
    end
    wire dp_valid,dp_ready,dp_write,dp_atomic,dp_execute,dp_cache_data;
    wire [63:0] dp_addr,dp_data,dp_rsp_data;
    wire [1:0] dp_size;
    wire [4:0] dp_amo;
    wire dp_rsp_valid,dp_rsp_ready,dp_rsp_error,dp_busy;
    reg dp_cached;
    always @(posedge clk) begin
        if(reset) dp_cached<=0;
        else if(dp_valid && dp_ready) dp_cached<=dp_cache_data;
    end
    rv64_mmu #(.TLB_ENABLE(TLB_ENABLE),.I_PIPELINE(I_PIPELINE)) fmmu(.clk(clk),.reset(reset),.privilege(privilege),.data_privilege(data_privilege),.satp(satp),.sum(sum),.mxr(mxr),.tlb_invalidate(tlb_invalidate),
        .u_valid(f_valid),.u_ready(f_ready),.u_addr(f_addr),.u_data(64'd0),.u_size(f_size),
        .u_write(1'b0),.u_execute(1'b1),.u_atomic(1'b0),.u_amo(5'd0),
        .u_rsp_valid(f_rsp_valid),.u_rsp_ready(f_rsp_ready),.u_rsp_data(f_rsp_data),.u_rsp_error(f_rsp_error),.u_rsp_cause(f_rsp_cause),.busy(ip_busy),.tlb_hit_event(itlb_hit_event),.tlb_miss_event(itlb_miss_event),.tlb_fill_event(itlb_fill_event),.walk_event(i_walk_event),
        .d_valid(ip_valid),.d_ready(ip_ready),.d_addr(ip_addr),.d_data(ip_data),.d_size(ip_size),
        .d_write(ip_write),.d_atomic(ip_atomic),.d_execute(ip_execute),.d_cache_data(ip_cache_data),.d_amo(ip_amo),
        .d_rsp_valid(ip_rsp_valid),.d_rsp_ready(ip_rsp_ready),.d_rsp_data(ip_rsp_data),.d_rsp_error(ip_rsp_error));
    rv64_mmu #(.TLB_ENABLE(TLB_ENABLE)) dmmu(.clk(clk),.reset(reset),.privilege(privilege),.data_privilege(data_privilege),.satp(satp),.sum(sum),.mxr(mxr),.tlb_invalidate(tlb_invalidate),
        .u_valid(d_valid),.u_ready(d_ready),.u_addr(d_addr),.u_data(d_data),.u_size(d_size),
        .u_write(d_write),.u_execute(1'b0),.u_atomic(d_atomic),.u_amo(d_amo),
        .u_rsp_valid(d_rsp_valid),.u_rsp_ready(d_rsp_ready),.u_rsp_data(d_rsp_data),.u_rsp_error(d_rsp_error),.u_rsp_cause(d_rsp_cause),.busy(dp_busy),.tlb_hit_event(dtlb_hit_event),.tlb_miss_event(dtlb_miss_event),.tlb_fill_event(dtlb_fill_event),.walk_event(d_walk_event),
        .d_valid(dp_valid),.d_ready(dp_ready),.d_addr(dp_addr),.d_data(dp_data),.d_size(dp_size),
        .d_write(dp_write),.d_atomic(dp_atomic),.d_execute(dp_execute),.d_cache_data(dp_cache_data),.d_amo(dp_amo),
        .d_rsp_valid(dp_rsp_valid),.d_rsp_ready(dp_rsp_ready),.d_rsp_data(dp_rsp_data),.d_rsp_error(dp_rsp_error));
    wire ic_ready,ic_rsp_valid,ic_rsp_ready,ic_rsp_error;
    wire [63:0] ic_rsp_data;
    wire ic_valid_out,ic_ready_out,ic_write_out,ic_atomic_out;
    wire [63:0] ic_addr_out,ic_data_out;
    wire [1:0] ic_size_out;
    wire [4:0] ic_amo_out;
    wire dc_ready,dc_rsp_valid,dc_rsp_ready,dc_rsp_error;
    wire [63:0] dc_rsp_data;
    wire dc_valid_out,dc_ready_out,dc_write_out,dc_atomic_out;
    wire [63:0] dc_addr_out,dc_data_out;
    wire [1:0] dc_size_out;
    wire [4:0] dc_amo_out;
    wire unused_dc_execute;
    wire [3:0] lane_valid,lane_ready,lane_rsp_valid,lane_rsp_ready;
    wire [63:0] physical_rsp_data;
    wire physical_rsp_error,physical_rsp_valid,physical_rsp_ready,physical_busy;
    assign ip_ready=ip_execute ? ic_ready : lane_ready[2];
    assign dp_ready=dp_cache_data ? dc_ready : lane_ready[3];
    assign ip_rsp_valid=ip_cached ? ic_rsp_valid : lane_rsp_valid[2];
    assign dp_rsp_valid=dp_cached ? dc_rsp_valid : lane_rsp_valid[3];
    assign ip_rsp_data=ip_cached ? ic_rsp_data : physical_rsp_data;
    assign dp_rsp_data=dp_cached ? dc_rsp_data : physical_rsp_data;
    assign ip_rsp_error=ip_cached ? ic_rsp_error : physical_rsp_error;
    assign dp_rsp_error=dp_cached ? dc_rsp_error : physical_rsp_error;
    assign ic_rsp_ready=ip_cached && ip_rsp_ready;
    assign dc_rsp_ready=dp_cached && dp_rsp_ready;
    rv64_icache #(.ENABLED(ICACHE_ENABLE),.EARLY_RESTART(EARLY_RESTART),.I_PIPELINE(I_PIPELINE),.HIT_UNDER_REFILL(ICACHE_HIT_UNDER_REFILL),.FILL_FORWARD(ICACHE_FILL_FORWARD),.WIDE_READ(ICACHE_WIDE_READ)) icache(.clk(clk),.reset(reset),.invalidate(icache_invalidate),
        .u_valid(ip_valid && ip_execute),.u_ready(ic_ready),.u_addr(ip_addr),.u_data(ip_data),.u_size(ip_size),
        .u_write(ip_write),.u_execute(1'b1),.u_atomic(ip_atomic),.u_amo(ip_amo),
        .u_rsp_valid(ic_rsp_valid),.u_rsp_ready(ic_rsp_ready),.u_rsp_data(ic_rsp_data),.u_rsp_error(ic_rsp_error),
        .d_valid(ic_valid_out),.d_ready(ic_ready_out),.d_addr(ic_addr_out),.d_data(ic_data_out),.d_size(ic_size_out),
        .d_write(ic_write_out),.d_atomic(ic_atomic_out),.d_amo(ic_amo_out),
        .d_rsp_valid(lane_rsp_valid[0]),.d_rsp_ready(lane_rsp_ready[0]),.d_rsp_data(physical_rsp_data),.d_rsp_error(physical_rsp_error),
        .hit_event(icache_hit_event),.miss_event(icache_miss_event),.refill_event(icache_refill_event),.miss_wait(icache_miss_wait),.bypass_event(icache_bypass_event),.refill_hit_event(icache_refill_hit_event),.fill_hit_event(icache_fill_hit_event));
    rv64_dcache #(.ENABLED(DCACHE_ENABLE),.EARLY_RESTART(DCACHE_EARLY_RESTART),.REFILL_FORWARD(DATA_REFILL_FORWARD)) dcache(.clk(clk),.reset(reset),.invalidate(reservation_invalidate),
        .u_valid(dp_valid && dp_cache_data),.u_ready(dc_ready),.u_addr(dp_addr),.u_data(dp_data),.u_size(dp_size),
        .u_write(dp_write),.u_execute(dp_execute),.u_cache_data(1'b1),.u_atomic(dp_atomic),.u_amo(dp_amo),
        .u_rsp_valid(dc_rsp_valid),.u_rsp_ready(dc_rsp_ready),.u_rsp_data(dc_rsp_data),.u_rsp_error(dc_rsp_error),
        .d_valid(dc_valid_out),.d_ready(dc_ready_out),.d_addr(dc_addr_out),.d_data(dc_data_out),.d_size(dc_size_out),
        .d_write(dc_write_out),.d_execute(unused_dc_execute),.d_atomic(dc_atomic_out),.d_amo(dc_amo_out),
        .d_rsp_valid(lane_rsp_valid[1]),.d_rsp_ready(lane_rsp_ready[1]),.d_rsp_data(physical_rsp_data),.d_rsp_error(physical_rsp_error),
        .hit_event(dcache_hit_event),.miss_event(dcache_miss_event),.refill_event(dcache_refill_event),.miss_wait(dcache_miss_wait),.write_event(dcache_write_event),.bypass_event(dcache_bypass_event));
    assign lane_valid={dp_valid && !dp_cache_data,ip_valid && !ip_execute,dc_valid_out,ic_valid_out};
    assign {dc_ready_out,ic_ready_out}=lane_ready[1:0];
    assign lane_rsp_ready[2]=!ip_cached && ip_rsp_ready;
    assign lane_rsp_ready[3]=!dp_cached && dp_rsp_ready;
    wire physical_valid,physical_ready,physical_write,physical_atomic;
    wire [63:0] physical_addr,physical_data;
    wire [1:0] physical_size;
    wire [4:0] physical_amo;
    rv64_physical_arbiter physical_arbiter(.clk(clk),.reset(reset),.c_valid(lane_valid),.c_ready(lane_ready),
        .c_addr({dp_addr,ip_addr,dc_addr_out,ic_addr_out}),.c_data({dp_data,ip_data,dc_data_out,ic_data_out}),
        .c_size({dp_size,ip_size,dc_size_out,ic_size_out}),.c_write({dp_write,ip_write,dc_write_out,ic_write_out}),
        .c_atomic({dp_atomic,ip_atomic,dc_atomic_out,ic_atomic_out}),.c_amo({dp_amo,ip_amo,dc_amo_out,ic_amo_out}),
        .c_rsp_valid(lane_rsp_valid),.c_rsp_ready(lane_rsp_ready),
        .u_valid(physical_valid),.u_ready(physical_ready),.u_addr(physical_addr),.u_data(physical_data),.u_size(physical_size),
        .u_write(physical_write),.u_atomic(physical_atomic),.u_amo(physical_amo),
        .u_rsp_valid(physical_rsp_valid),.u_rsp_ready(physical_rsp_ready),.busy(physical_busy),
        .data_blocked_by_fetch(data_blocked_by_fetch),.fetch_blocked_by_data(fetch_blocked_by_data));
    rv64_atomic_adapter atomics(.clk(clk),.reset(reset),.clear_reservation(clear_reservation),
        .u_valid(physical_valid),.u_ready(physical_ready),.u_addr(physical_addr),.u_data(physical_data),.u_write(physical_write),
        .u_atomic(physical_atomic),.u_amo(physical_amo),.u_size(physical_size),
        .u_rsp_valid(physical_rsp_valid),.u_rsp_ready(physical_rsp_ready),.u_rsp_data(physical_rsp_data),.u_rsp_error(physical_rsp_error),
        .d_valid(req_valid),.d_ready(req_ready),.d_addr(req_addr),.d_data(req_wdata),.d_write(req_write),.d_store_check(req_store_check),.d_size(req_size),
        .d_rsp_valid(rsp_valid),.d_rsp_ready(rsp_ready),.d_rsp_data(rsp_rdata),.d_rsp_error(rsp_error),.bus_lock(bus_lock));
    // Drain both translators, cache background fills and physical ownership before serial commit.
    assign busy=ip_busy || dp_busy || physical_busy || icache_miss_wait || dcache_miss_wait;
    wire unused_ip_cache_data=ip_cache_data;
    end endgenerate
endmodule
