module rv64_amo_alu (
    input wire [63:0] old_value, operand,
    input wire word_op,
    input wire [4:0] operation,
    output wire [63:0] new_value
);
    wire [63:0] a=word_op ? {32'd0,old_value[31:0]} : old_value;
    wire [63:0] b=word_op ? {32'd0,operand[31:0]} : operand;
    wire [63:0] sa=word_op ? {{32{a[31]}},a[31:0]} : a;
    wire [63:0] sb=word_op ? {{32{b[31]}},b[31:0]} : b;
    reg [63:0] value;
    always @* begin
        case (operation)
            0: value=a+b;
            1: value=b;
            4: value=a^b;
            8: value=a|b;
            12: value=a&b;
            16: value=$signed(sa)<$signed(sb) ? a : b;
            20: value=$signed(sa)>$signed(sb) ? a : b;
            24: value=a<b ? a : b;
            28: value=a>b ? a : b;
            default: value=0;
        endcase
    end
    assign new_value=word_op ? {32'd0,value[31:0]} : value;
endmodule
