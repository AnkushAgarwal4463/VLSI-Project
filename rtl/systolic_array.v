// systolic_array.v -- Parameterized NxN Systolic Array Grid
`default_nettype none

module systolic_array #(
    parameter N     = 4,
    parameter WIDTH = 8
) (
    input  wire                     clk,
    input  wire                     rst_n,
    input  wire [N*WIDTH-1:0]       a_edge_in,
    input  wire [N*WIDTH-1:0]       b_edge_in,
    output wire [N*N*2*WIDTH-1:0]   acc_flat
);

    // Internal 2D interconnect arrays
    wire [WIDTH-1:0]   a_wire   [0:N-1][0:N];
    wire [WIDTH-1:0]   b_wire   [0:N][0:N-1];
    wire [2*WIDTH-1:0] acc_wire [0:N-1][0:N-1];

    // Connect top and left boundary inputs
    genvar r, c;
    generate
        for (r = 0; r < N; r = r + 1) begin : g_row_edge
            assign a_wire[r][0] = a_edge_in[r*WIDTH +: WIDTH];
        end

        for (c = 0; c < N; c = c + 1) begin : g_col_edge
            assign b_wire[0][c] = b_edge_in[c*WIDTH +: WIDTH];
        end

        // Instantiate Processing Element (PE) matrix
        for (r = 0; r < N; r = r + 1) begin : g_row
            for (c = 0; c < N; c = c + 1) begin : g_col
                pe #(
                    .WIDTH(WIDTH)
                ) pe_inst (
                    .clk     (clk),
                    .rst_n   (rst_n),
                    .a_in    (a_wire[r][c]),
                    .b_in    (b_wire[r][c]),
                    .a_out   (a_wire[r][c+1]),
                    .b_out   (b_wire[r+1][c]),
                    .acc_out (acc_wire[r][c])
                );

                // Flatten accumulated output matrix into 1D output bus
                assign acc_flat[(r*N + c)*2*WIDTH +: 2*WIDTH] = acc_wire[r][c];
            end
        end
    endgenerate

endmodule

`default_nettype wire
