// Single-master atomic adapter. The downstream fabric MUST honor bus_lock when shared.
module rv64_atomic_adapter (
    input wire clk, reset, clear_reservation, snoop_write,
    input wire [63:3] snoop_addr,
    input wire u_valid, output wire u_ready,
    input wire [63:0] u_addr,u_data,
    input wire u_write,u_atomic, input wire [4:0] u_amo, input wire [1:0] u_size,
    output wire u_rsp_valid, input wire u_rsp_ready,
    output wire [63:0] u_rsp_data,u_rsp_store_data, output wire u_rsp_error,
    output wire d_valid, input wire d_ready,
    output wire [63:0] d_addr,d_data, output wire d_write,d_store_check, output wire [1:0] d_size,
    input wire d_rsp_valid, output wire d_rsp_ready,
    input wire [63:0] d_rsp_data, input wire d_rsp_error,
    output wire bus_lock
);
    localparam [2:0] IDLE=0, RESPONSE=1, AMO_WRITE=2, AMO_RESPONSE=3, SC_FAIL=4;
    reg [2:0] state;
    reg atomic_pending,write_pending;
    reg [4:0] amo;
    reg [63:0] address,data,old_data,new_data,reserved_address;
    reg [1:0] size,reserved_size;
    reg reserved;
    wire is_rmw=atomic_pending && amo!=2 && amo!=3;
    wire is_sc=atomic_pending && amo==3;
    // All cluster requests are naturally aligned and at most eight bytes.
    wire snoop_hit=snoop_write && snoop_addr==reserved_address[63:3];
    wire sc_can_store=reserved && !clear_reservation && !snoop_hit && reserved_address==address && reserved_size==size;
    wire [63:0] computed;
    rv64_amo_alu arithmetic(.old_value(d_rsp_data),.operand(data),.word_op(size==2),.operation(amo),.new_value(computed));
    assign d_valid=(state==IDLE && u_valid) || state==AMO_WRITE;
    assign d_addr=state==IDLE ? u_addr : address;
    assign d_data=state==IDLE ? u_data : new_data;
    assign d_size=state==IDLE ? u_size : size;
    assign d_write=state==AMO_WRITE || (state==IDLE && u_write && !u_atomic);
    assign d_store_check=state==IDLE && u_valid && u_atomic && u_amo==3;
    assign u_ready=state==IDLE && d_ready;
    assign u_rsp_valid=state==SC_FAIL || (d_rsp_valid && ((state==RESPONSE && ((!is_rmw && !is_sc) || d_rsp_error)) || state==AMO_RESPONSE));
    // The RMW store payload remains registered through the response handshake.
    assign u_rsp_store_data=new_data;
    assign u_rsp_data=state==SC_FAIL ? 64'd1 : state==AMO_RESPONSE ? (is_sc ? 64'd0 : old_data) : d_rsp_data;
    assign u_rsp_error=state==SC_FAIL ? 1'b0 : d_rsp_error;
    assign d_rsp_ready=(state==RESPONSE && (is_rmw || is_sc) && !d_rsp_error) || ((state==RESPONSE || state==AMO_RESPONSE) && u_rsp_ready);
    assign bus_lock=(state==IDLE ? u_valid && u_atomic : atomic_pending && state!=SC_FAIL);
    always @(posedge clk) begin
        if (reset) begin
            state<=IDLE; atomic_pending<=0; write_pending<=0; amo<=0; address<=0; data<=0;
            old_data<=0; new_data<=0; size<=0; reserved<=0; reserved_address<=0; reserved_size<=0;
        end else begin
            if (clear_reservation || snoop_hit) reserved<=0;
            case (state)
                IDLE: if (u_valid && u_ready) begin
                    address<=u_addr; data<=u_data; size<=u_size; amo<=u_amo;
                    atomic_pending<=u_atomic; write_pending<=u_write;
                    if (u_write && !(u_atomic && u_amo==3)) reserved<=0; // conservative invalidation is legal
                    state<=RESPONSE; // SC first obtains store permission without modifying memory
                end
                RESPONSE: if (d_rsp_valid && d_rsp_ready) begin
                    if (is_sc && !d_rsp_error) begin
                        reserved<=0;
                        if (sc_can_store) begin new_data<=data; state<=AMO_WRITE; end
                        else state<=SC_FAIL;
                    end else if (is_rmw && !d_rsp_error) begin
                        old_data<=d_rsp_data; new_data<=computed; state<=AMO_WRITE;
                    end else begin
                        if (atomic_pending && amo==2 && !d_rsp_error && !clear_reservation &&
                            !(snoop_write && snoop_addr==address[63:3])) begin
                            reserved<=1; reserved_address<=address; reserved_size<=size;
                        end
                        if (write_pending) reserved<=0;
                        state<=IDLE;
                    end
                end
                AMO_WRITE: if (d_ready) state<=AMO_RESPONSE;
                AMO_RESPONSE: if (d_rsp_valid && u_rsp_ready) state<=IDLE;
                SC_FAIL: if (u_rsp_ready) state<=IDLE;
                default: state<=IDLE;
            endcase
        end
    end
endmodule
