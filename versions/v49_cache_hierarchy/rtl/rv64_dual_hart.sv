// Two harts with private split L1 and a shared L2. Both start at PC 0.
module rv64_dual_hart #(parameter L1D_ENABLE=1, parameter L2_ENABLE=1) (
    input wire clk, reset,
    input wire [127:0] irq_pending,
    input wire [63:0] time_value,
    output wire mem_valid,
    input wire mem_ready,
    output wire [63:0] mem_addr, mem_wdata,
    output wire [1:0] mem_size,
    output wire mem_write, mem_store_check,
    input wire mem_rsp_valid, mem_rsp_error,
    output wire mem_rsp_ready,
    input wire [63:0] mem_rsp_data,
    output wire [1:0] commit_valid, commit2_valid, trap_valid,
    output wire [63:0] commit_insn,
    output wire [127:0] instret,
    output wire [1:0] l1d_hit, l1d_miss,
    output wire l2_hit, l2_fill
);
    wire [1:0] req_valid, req_ready, req_write, req_store_check, bus_lock;
    wire [1:0] rsp_valid, rsp_ready, snoop_write;
    wire [127:0] req_addr, req_wdata;
    wire [3:0] req_size;
    wire [63:3] snoop_addr;
    wire l2_valid, l2_ready, l2_write, l2_store_check, l2_uncached;
    wire l2_rsp_valid, l2_rsp_ready, l2_rsp_error;
    wire [63:0] l2_addr, l2_wdata, l2_rsp_data;
    wire [1:0] l2_size;

    for (genvar hart=0; hart<2; hart=hart+1) begin : harts
        /* verilator lint_off PINMISSING */
        rv64_core #(.DCACHE_ENABLE(L1D_ENABLE), .HART_ID(64'(hart))) core (
            .clk(clk), .reset(reset), .irq_pending(irq_pending[hart*64+:64]), .time_value(time_value),
            .reservation_invalidate(1'b0), .snoop_write(snoop_write[hart]), .snoop_addr(snoop_addr),
            .bus_lock(bus_lock[hart]), .req_valid(req_valid[hart]), .req_ready(req_ready[hart]),
            .req_addr(req_addr[hart*64+:64]), .req_wdata(req_wdata[hart*64+:64]), .req_size(req_size[hart*2+:2]),
            .req_write(req_write[hart]), .req_store_check(req_store_check[hart]),
            .rsp_valid(rsp_valid[hart]), .rsp_ready(rsp_ready[hart]),
            .rsp_rdata(l2_rsp_data), .rsp_error(l2_rsp_error),
            .commit_valid(commit_valid[hart]), .commit_insn(commit_insn[hart*32+:32]),
            .dcache_hit_event(l1d_hit[hart]), .dcache_miss_event(l1d_miss[hart]),
            .commit2_valid(commit2_valid[hart]), .trap_valid(trap_valid[hart]), .instret(instret[hart*64+:64])
        );
        /* verilator lint_on PINMISSING */
    end

    rv64_shared_bus fabric (
        .clk(clk), .reset(reset), .req_valid(req_valid), .req_write(req_write),
        .req_store_check(req_store_check), .bus_lock(bus_lock), .req_addr(req_addr),
        .req_wdata(req_wdata), .req_size(req_size), .req_ready(req_ready),
        .rsp_valid(rsp_valid), .rsp_ready(rsp_ready), .snoop_write(snoop_write),
        .mem_valid(l2_valid), .mem_ready(l2_ready), .mem_addr(l2_addr), .mem_wdata(l2_wdata),
        .mem_size(l2_size), .mem_write(l2_write), .mem_store_check(l2_store_check), .mem_uncached(l2_uncached),
        .mem_rsp_valid(l2_rsp_valid), .mem_rsp_error(l2_rsp_error), .mem_rsp_ready(l2_rsp_ready),
        .snoop_addr(snoop_addr)
    );
    if (L2_ENABLE!=0) begin : cache
        rv64_l2_cache shared_l2 (
            .clk(clk), .reset(reset),
            .u_valid(l2_valid), .u_ready(l2_ready), .u_addr(l2_addr), .u_wdata(l2_wdata),
            .u_size(l2_size), .u_write(l2_write), .u_store_check(l2_store_check), .u_uncached(l2_uncached),
            .u_rsp_valid(l2_rsp_valid), .u_rsp_ready(l2_rsp_ready), .u_rsp_data(l2_rsp_data), .u_rsp_error(l2_rsp_error),
            .d_valid(mem_valid), .d_ready(mem_ready), .d_addr(mem_addr), .d_wdata(mem_wdata),
            .d_size(mem_size), .d_write(mem_write), .d_store_check(mem_store_check),
            .d_rsp_valid(mem_rsp_valid), .d_rsp_ready(mem_rsp_ready), .d_rsp_data(mem_rsp_data), .d_rsp_error(mem_rsp_error),
            .hit_event(l2_hit), .fill_event(l2_fill)
        );
    end else begin : bypass
        wire unused_uncached=l2_uncached;
        assign mem_valid=l2_valid;
        assign l2_ready=mem_ready;
        assign mem_addr=l2_addr;
        assign mem_wdata=l2_wdata;
        assign mem_size=l2_size;
        assign mem_write=l2_write;
        assign mem_store_check=l2_store_check;
        assign l2_rsp_valid=mem_rsp_valid;
        assign mem_rsp_ready=l2_rsp_ready;
        assign l2_rsp_data=mem_rsp_data;
        assign l2_rsp_error=mem_rsp_error;
        assign l2_hit=0;
        assign l2_fill=0;
    end
endmodule
