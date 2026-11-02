// Data-priority, one outstanding transaction. Accepts a client request into
// holding registers even when the MMU is blocked, preserving external stability.
module rv64_bus_arbiter (
    input wire clk,reset,
    input wire f_valid,output wire f_ready,input wire [63:0] f_addr,input wire [1:0] f_size,
    output wire f_rsp_valid,input wire f_rsp_ready,
    input wire d_valid,output wire d_ready,input wire [63:0] d_addr,d_data,
    input wire [1:0] d_size,input wire d_write,d_atomic,input wire [4:0] d_amo,
    output wire d_rsp_valid,input wire d_rsp_ready,
    output wire u_valid,input wire u_ready,output wire [63:0] u_addr,u_data,
    output wire [1:0] u_size,output wire u_write,u_execute,u_atomic,output wire [4:0] u_amo,
    input wire u_rsp_valid,output wire u_rsp_ready,output wire busy,
    output wire data_blocked_by_fetch,fetch_blocked_by_data
);
    localparam [1:0] IDLE=0,REQUEST=1,RESPONSE=2;
    reg [1:0] state;
    reg owner_data,write_access,atomic_access;
    reg [63:0] address,data;
    reg [1:0] size;
    reg [4:0] amo;
    assign busy=state!=IDLE;
    assign data_blocked_by_fetch=d_valid && state!=IDLE && !owner_data;
    assign fetch_blocked_by_data=f_valid && ((state!=IDLE && owner_data) || (state==IDLE && d_valid));
    assign f_ready=!reset && state==IDLE && !d_valid;
    assign d_ready=!reset && state==IDLE;
    assign u_valid=!reset && (state==REQUEST || (state==IDLE && (d_valid || f_valid)));
    assign u_addr=state==IDLE ? (d_valid ? d_addr : f_addr) : address;
    assign u_data=state==IDLE ? (d_valid ? d_data : 64'd0) : data;
    assign u_size=state==IDLE ? (d_valid ? d_size : f_size) : size;
    assign u_write=state==IDLE ? d_valid && d_write : write_access;
    assign u_atomic=state==IDLE ? d_valid && d_atomic : atomic_access;
    assign u_amo=state==IDLE ? (d_valid ? d_amo : 5'd0) : amo;
    assign u_execute=state==IDLE ? !d_valid : !owner_data;
    assign f_rsp_valid=state==RESPONSE && !owner_data && u_rsp_valid;
    assign d_rsp_valid=state==RESPONSE && owner_data && u_rsp_valid;
    assign u_rsp_ready=state==RESPONSE && (owner_data ? d_rsp_ready : f_rsp_ready);
    always @(posedge clk) begin
        if (reset) begin
            state<=IDLE; owner_data<=0; address<=0; data<=0; size<=0;
            write_access<=0; atomic_access<=0; amo<=0;
        end else case (state)
            IDLE: if (u_valid) begin
                owner_data<=d_valid; address<=u_addr; data<=u_data; size<=u_size;
                write_access<=u_write; atomic_access<=u_atomic; amo<=u_amo;
                state<=u_ready ? RESPONSE : REQUEST;
            end
            REQUEST: if (u_ready) state<=RESPONSE;
            RESPONSE: if (u_rsp_valid && u_rsp_ready) state<=IDLE;
            default: state<=IDLE;
        endcase
    end
endmodule
