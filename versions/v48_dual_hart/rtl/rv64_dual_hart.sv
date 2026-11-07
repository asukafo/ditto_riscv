// Bare-metal dual-hart prototype. Both harts start at PC 0 and read mhartid.
module rv64_dual_hart (
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
    output wire [127:0] instret
);
    wire [1:0] req_valid, req_ready, req_write, req_store_check, bus_lock;
    wire [1:0] rsp_valid, rsp_ready, snoop_write;
    wire [127:0] req_addr, req_wdata;
    wire [3:0] req_size;
    wire [63:3] snoop_addr;

    for (genvar hart=0; hart<2; hart=hart+1) begin : harts
        // Private I-cache for immutable code. Shared data always goes to memory.
        /* verilator lint_off PINMISSING */
        rv64_core #(.DCACHE_ENABLE(0), .HART_ID(64'(hart))) core (
            .clk(clk), .reset(reset), .irq_pending(irq_pending[hart*64+:64]), .time_value(time_value),
            .reservation_invalidate(1'b0), .snoop_write(snoop_write[hart]), .snoop_addr(snoop_addr),
            .bus_lock(bus_lock[hart]), .req_valid(req_valid[hart]), .req_ready(req_ready[hart]),
            .req_addr(req_addr[hart*64+:64]), .req_wdata(req_wdata[hart*64+:64]), .req_size(req_size[hart*2+:2]),
            .req_write(req_write[hart]), .req_store_check(req_store_check[hart]),
            .rsp_valid(rsp_valid[hart]), .rsp_ready(rsp_ready[hart]),
            .rsp_rdata(mem_rsp_data), .rsp_error(mem_rsp_error),
            .commit_valid(commit_valid[hart]), .commit_insn(commit_insn[hart*32+:32]),
            .commit2_valid(commit2_valid[hart]), .trap_valid(trap_valid[hart]), .instret(instret[hart*64+:64])
        );
        /* verilator lint_on PINMISSING */
    end

    rv64_shared_bus fabric (
        .clk(clk), .reset(reset), .req_valid(req_valid), .req_write(req_write),
        .req_store_check(req_store_check), .bus_lock(bus_lock), .req_addr(req_addr),
        .req_wdata(req_wdata), .req_size(req_size), .req_ready(req_ready),
        .rsp_valid(rsp_valid), .rsp_ready(rsp_ready), .snoop_write(snoop_write),
        .mem_valid(mem_valid), .mem_ready(mem_ready), .mem_addr(mem_addr), .mem_wdata(mem_wdata),
        .mem_size(mem_size), .mem_write(mem_write), .mem_store_check(mem_store_check),
        .mem_rsp_valid(mem_rsp_valid), .mem_rsp_error(mem_rsp_error), .mem_rsp_ready(mem_rsp_ready),
        .snoop_addr(snoop_addr)
    );
endmodule
