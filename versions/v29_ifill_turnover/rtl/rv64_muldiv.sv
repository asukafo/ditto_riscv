// Iterative radix-2 multiply/divide. Deliberately avoids a giant combinational divider.
module rv64_muldiv (
    input wire clk, reset, start, word_op,
    input wire [2:0] operation,
    input wire [63:0] a,b,
    output reg busy, done,
    output reg [63:0] result
);
    reg [2:0] op;
    reg word_mode, negative_product, negative_quotient, negative_remainder, zero_divisor;
    reg [6:0] remaining;
    reg [127:0] product, multiplicand;
    reg [63:0] multiplier, dividend, divisor;
    reg [62:0] quotient;
    reg [63:0] remainder;
    wire signed_a=(operation==1 || operation==2 || operation==4 || operation==6);
    wire signed_b=(operation==1 || operation==4 || operation==6);
    wire [63:0] operand_a=word_op ? ((operation==4 || operation==6) ? {{32{a[31]}},a[31:0]} : {32'd0,a[31:0]}) : a;
    wire [63:0] operand_b=word_op ? ((operation==4 || operation==6) ? {{32{b[31]}},b[31:0]} : {32'd0,b[31:0]}) : b;
    wire neg_a=signed_a && operand_a[63];
    wire neg_b=signed_b && operand_b[63];
    wire [63:0] magnitude_a=neg_a ? -operand_a : operand_a;
    wire [63:0] magnitude_b=neg_b ? -operand_b : operand_b;
    wire [127:0] sum_product=product+(multiplier[0] ? multiplicand : 128'd0);
    wire [127:0] final_product=negative_product ? -sum_product : sum_product;
    wire [64:0] trial={remainder,dividend[63]};
    wire subtract=trial>={1'b0,divisor};
    wire [64:0] next_remainder=subtract ? trial-{1'b0,divisor} : trial;
    wire unused_remainder_carry=next_remainder[64]; // remainder < divisor (or dividend when dividing by zero)
    wire [63:0] next_quotient={quotient,subtract};
    wire [63:0] final_quotient=(negative_quotient && !zero_divisor) ? -next_quotient : next_quotient;
    wire [63:0] final_remainder=negative_remainder ? -next_remainder[63:0] : next_remainder[63:0];
    wire [63:0] selected=op[2] ? (op[1] ? final_remainder : final_quotient) : (op==0 ? final_product[63:0] : final_product[127:64]);
    always @(posedge clk) begin
        if (reset) begin
            busy<=0; done<=0; result<=0; op<=0; word_mode<=0; remaining<=0;
            product<=0; multiplicand<=0; multiplier<=0; dividend<=0; divisor<=0; quotient<=0; remainder<=0;
            negative_product<=0; negative_quotient<=0; negative_remainder<=0; zero_divisor<=0;
        end else begin
            done<=0;
            if (start && !busy) begin
                busy<=1; op<=operation; word_mode<=word_op; remaining<=word_op ? 7'd32 : 7'd64;
                product<=0; multiplicand<={64'd0,magnitude_a}; multiplier<=magnitude_b;
                dividend<=word_op ? {magnitude_a[31:0],32'd0} : magnitude_a;
                divisor<=magnitude_b; quotient<=0; remainder<=0;
                negative_product<=neg_a^neg_b; negative_quotient<=neg_a^neg_b;
                negative_remainder<=neg_a; zero_divisor<=magnitude_b==0;
            end else if (busy) begin
                remaining<=remaining-1;
                if (op[2]) begin
                    dividend<=dividend<<1; quotient<=next_quotient[62:0]; remainder<=next_remainder[63:0];
                end else begin product<=sum_product; multiplicand<=multiplicand<<1; multiplier<=multiplier>>1; end
                if (remaining==1) begin
                    result<=word_mode ? {{32{selected[31]}},selected[31:0]} : selected;
                    busy<=0; done<=1;
                end
            end
        end
    end
endmodule
