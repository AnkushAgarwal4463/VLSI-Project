# ==============================================================================
# Systolic Array OpenROAD Physical Design Flow
#
# Technology : SKY130A
# Standard cells : sky130_fd_sc_hd
#
# Outputs per run:
#   final.odb
#   route.guide
#   timing_setup.rpt
#   timing_hold.rpt
#   wire_length.rpt
#   route_status.rpt
#   placement.rpt
# ==============================================================================


# ==============================================================================
# 1. Read Environment Variables
# ==============================================================================

if {[info exists ::env(ARRAY_SIZE)]} {
    set ARRAY_SIZE $::env(ARRAY_SIZE)
} else {
    set ARRAY_SIZE 4
}

if {[info exists ::env(DATA_WIDTH)]} {
    set DATA_WIDTH $::env(DATA_WIDTH)
} else {
    set DATA_WIDTH 8
}

if {[info exists ::env(UTIL)]} {
    set UTIL $::env(UTIL)
} else {
    set UTIL 50
}

if {[info exists ::env(CLK_PERIOD)]} {
    set CLK_PERIOD $::env(CLK_PERIOD)
} else {
    set CLK_PERIOD 5.0
}

if {[info exists ::env(RUN_TAG)]} {
    set RUN_TAG $::env(RUN_TAG)
} else {
    set RUN_TAG "run_test"
}

if {[info exists ::env(SITE)] && $::env(SITE) != ""} {
    set site_name $::env(SITE)
} else {
    set site_name "unithd"
}


# ==============================================================================
# 2. Validate Parameters
# ==============================================================================

set util_decimal [expr {$UTIL / 100.0}]

if {$util_decimal <= 0.0 || $util_decimal >= 1.0} {
    puts "\[ERROR\] Invalid utilization: $UTIL"
    exit 1
}

if {$CLK_PERIOD <= 0.0} {
    puts "\[ERROR\] Invalid clock period: $CLK_PERIOD"
    exit 1
}

if {$ARRAY_SIZE <= 0} {
    puts "\[ERROR\] Invalid array size: $ARRAY_SIZE"
    exit 1
}

if {$DATA_WIDTH <= 0} {
    puts "\[ERROR\] Invalid data width: $DATA_WIDTH"
    exit 1
}


# ==============================================================================
# 3. Run Directory
# ==============================================================================

set run_dir "systolic_project/runs/$RUN_TAG"

file mkdir $run_dir

puts "=============================================================="
puts "\[INFO\] Systolic Array OpenROAD Flow"
puts "=============================================================="
puts "ARRAY_SIZE : $ARRAY_SIZE"
puts "DATA_WIDTH : $DATA_WIDTH"
puts "UTIL       : $UTIL%"
puts "CLK_PERIOD : $CLK_PERIOD ns"
puts "RUN_TAG    : $RUN_TAG"
puts "SITE       : $site_name"
puts "RUN_DIR    : $run_dir"
puts "=============================================================="


# ==============================================================================
# 4. SKY130 Technology Files
# ==============================================================================

set pdk_dir "./conda-env/share/pdk/sky130A"

set tech_lef \
    "${pdk_dir}/libs.ref/sky130_fd_sc_hd/techlef/sky130_fd_sc_hd__nom.tlef"

set std_cell_lef \
    "${pdk_dir}/libs.ref/sky130_fd_sc_hd/lef/sky130_fd_sc_hd.lef"

# ------------------------------------------------------------------------------
# Use the same Liberty file selected by GitHub Actions/Yosys whenever possible.
# This prevents synthesis and OpenROAD from using different timing libraries.
# ------------------------------------------------------------------------------

if {[info exists ::env(LIB_FILE)] && $::env(LIB_FILE) != ""} {

    set lib_file $::env(LIB_FILE)

} else {

    set lib_file \
        "${pdk_dir}/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_5v00.lib"
}

set netlist_verilog \
    "systolic_project/synth/systolic_netlist.v"


# ==============================================================================
# 5. Verify Required Files
# ==============================================================================

puts "\[INFO\] Checking technology files..."

if {![file exists $tech_lef]} {
    puts "\[ERROR\] Tech LEF not found:"
    puts "         $tech_lef"
    exit 1
}

if {![file exists $std_cell_lef]} {
    puts "\[ERROR\] Standard-cell LEF not found:"
    puts "         $std_cell_lef"
    exit 1
}

if {![file exists $lib_file]} {
    puts "\[ERROR\] Liberty file not found:"
    puts "         $lib_file"
    exit 1
}

if {![file exists $netlist_verilog]} {
    puts "\[ERROR\] Synthesized netlist not found:"
    puts "         $netlist_verilog"
    exit 1
}

puts "\[INFO\] Technology files verified."
puts "\[INFO\] Liberty:"
puts "         $lib_file"


# ==============================================================================
# 6. Read Technology and Netlist
# ==============================================================================

puts "\[INFO\] Reading Liberty..."
read_liberty $lib_file

puts "\[INFO\] Reading technology LEF..."
read_lef $tech_lef

puts "\[INFO\] Reading standard-cell LEF..."
read_lef $std_cell_lef

puts "\[INFO\] Reading synthesized netlist..."
read_verilog $netlist_verilog


# ==============================================================================
# 7. Link Design
# ==============================================================================

puts "\[INFO\] Linking design systolic_array..."

link_design "systolic_array"

current_design "systolic_array"

puts "\[INFO\] Design linked successfully."


# ==============================================================================
# 8. Calculate Standard-Cell Area
# ==============================================================================

set total_cell_area 0.0

foreach inst [get_cells -hierarchical *] {

    if {![catch {
        get_property -quiet $inst lib_cell
    } cell_master]} {

        if {$cell_master != ""} {

            set area [get_property -quiet $cell_master area]

            if {$area != "" && $area > 0} {

                set total_cell_area \
                    [expr {$total_cell_area + $area}]
            }
        }
    }
}

puts "\[INFO\] Extracted standard-cell area:"
puts "         ${total_cell_area} um^2"


# ==============================================================================
# 9. Area Fallback
# ==============================================================================

if {$total_cell_area <= 0.0} {

    set inst_count [llength [get_cells -hierarchical *]]

    # Only a fallback to prevent the flow from stopping.
    # This value should be treated as estimated rather than measured area.
    set average_cell_area 12.0

    set total_cell_area \
        [expr {$inst_count * $average_cell_area}]

    puts "\[WARNING\] Cell-area extraction returned zero."
    puts "\[WARNING\] Using estimated fallback area:"
    puts "            Instances = $inst_count"
    puts "            Area      = ${total_cell_area} um^2"
}


# ==============================================================================
# 10. Dynamic Floorplan
# ==============================================================================

# Additional area allowance for placement/routing overhead.
set buffered_cell_area \
    [expr {$total_cell_area * 1.15}]

set required_core_area \
    [expr {$buffered_cell_area / $util_decimal}]

set core_dim \
    [expr {sqrt($required_core_area)}]


# ==============================================================================
# 11. Snap Core to SKY130 HD Site Grid
# ==============================================================================

set site_height 2.72

set core_dim_snapped \
    [expr {ceil($core_dim / $site_height) * $site_height}]


# Minimum practical core dimension for this experiment.
if {$core_dim_snapped < 150.0} {
    set core_dim_snapped 150.0
}


# ==============================================================================
# 12. Core Margin
# ==============================================================================

if {$UTIL >= 60} {

    set raw_margin 50.0

} elseif {$UTIL >= 40} {

    set raw_margin 35.0

} else {

    set raw_margin 25.0
}

set core_margin \
    [expr {ceil($raw_margin / $site_height) * $site_height}]


# ==============================================================================
# 13. Die and Core Coordinates
# ==============================================================================

set core_x0 $core_margin
set core_y0 $core_margin

set core_x1 \
    [expr {$core_x0 + $core_dim_snapped}]

set core_y1 \
    [expr {$core_y0 + $core_dim_snapped}]

set die_x0 0.0
set die_y0 0.0

set die_x1 \
    [expr {$core_x1 + $core_margin}]

set die_y1 \
    [expr {$core_y1 + $core_margin}]

set actual_core_area \
    [expr {
        ($core_x1 - $core_x0) *
        ($core_y1 - $core_y0)
    }]

set projected_util \
    [expr {
        ($total_cell_area / $actual_core_area) * 100.0
    }]


puts "=============================================================="
puts "\[INFO\] Floorplan"
puts "=============================================================="
puts "Cell area       : $total_cell_area um^2"
puts "Buffered area   : $buffered_cell_area um^2"
puts "Target util     : $UTIL%"
puts "Core dimension  : $core_dim_snapped um"
puts "Core area       : $actual_core_area um^2"
puts "Projected util  : [format "%.2f" $projected_util]%"
puts "Die             : $die_x0 $die_y0 $die_x1 $die_y1"
puts "Core            : $core_x0 $core_y0 $core_x1 $core_y1"
puts "=============================================================="


# ==============================================================================
# 14. Initialize Floorplan
# ==============================================================================

puts "\[INFO\] Initializing floorplan..."

if {[catch {

    initialize_floorplan \
        -die_area "$die_x0 $die_y0 $die_x1 $die_y1" \
        -core_area "$core_x0 $core_y0 $core_x1 $core_y1" \
        -site $site_name

} err]} {

    puts "\[WARNING\] Site '$site_name' failed:"
    puts "           $err"

    puts "\[INFO\] Trying fallback site 'unithd'..."

    if {[catch {

        initialize_floorplan \
            -die_area "$die_x0 $die_y0 $die_x1 $die_y1" \
            -core_area "$core_x0 $core_y0 $core_x1 $core_y1" \
            -site "unithd"

    } err2]} {

        puts "\[ERROR\] initialize_floorplan failed."
        puts "$err2"
        exit 1
    }
}


# ==============================================================================
# 15. Routing Tracks
# ==============================================================================

puts "\[INFO\] Creating routing tracks..."

if {[catch {

    make_tracks

} err]} {

    puts "\[ERROR\] make_tracks failed:"
    puts "$err"
    exit 1
}


# ==============================================================================
# 16. Timing Constraints
# ==============================================================================

puts "\[INFO\] Creating clock..."

create_clock \
    -name clk \
    -period $CLK_PERIOD \
    [get_ports clk]


# ------------------------------------------------------------------------------
# Input delay
# ------------------------------------------------------------------------------

set in_ports \
    [get_ports * -filter "direction == input && name != clk"]

if {[llength $in_ports] > 0} {

    set_input_delay \
        -clock clk \
        0.2 \
        $in_ports
}


# ------------------------------------------------------------------------------
# Output delay
# ------------------------------------------------------------------------------

set out_ports [all_outputs]

if {[llength $out_ports] > 0} {

    set_output_delay \
        -clock clk \
        0.2 \
        $out_ports
}


# ==============================================================================
# 17. Global Placement
# ==============================================================================

set place_density $util_decimal

# OpenROAD placement becomes increasingly difficult at very high density.
# The experiment currently supports requested utilization values up to 70%.
if {$place_density > 0.70} {
    set place_density 0.70
}

puts "\[INFO\] Requested utilization : $UTIL%"
puts "\[INFO\] Placement density    : $place_density"

global_placement \
    -density $place_density


# ==============================================================================
# 18. Pin Placement
# ==============================================================================

puts "\[INFO\] Placing IO pins..."

set io_hor_layers [list met3 met5]
set io_ver_layers [list met2 met4]

if {[catch {

    place_pins \
        -hor_layers $io_hor_layers \
        -ver_layers $io_ver_layers

} err]} {

    puts "\[WARNING\] Pin placement warning:"
    puts "$err"
}


# ==============================================================================
# 19. Detailed Placement
# ==============================================================================

puts "\[INFO\] Running detailed placement..."

if {[catch {

    detailed_placement

} err]} {

    puts "\[ERROR\] Detailed placement failed:"
    puts "$err"
    exit 1
}

check_placement


# ==============================================================================
# 20. Initial Placement Report
# ==============================================================================

puts "\[INFO\] Writing placement report..."

if {[catch {

    report_design_area \
        > "${run_dir}/placement.rpt"

} err]} {

    puts "\[WARNING\] Placement/area report failed:"
    puts "$err"
}


# ==============================================================================
# 21. Design Repair
# ==============================================================================

puts "\[INFO\] Running design repair..."

if {[catch {

    repair_design

} err]} {

    puts "\[WARNING\] Design repair failed:"
    puts "$err"
}


# ==============================================================================
# 22. Timing Repair
# ==============================================================================

puts "\[INFO\] Running timing repair..."

if {[catch {

    repair_timing \
        -setup \
        -setup_margin 0.2

} err]} {

    puts "\[WARNING\] Timing repair failed:"
    puts "$err"
}


# ==============================================================================
# 23. Re-Legalize Placement
# ==============================================================================

puts "\[INFO\] Re-running detailed placement..."

if {[catch {

    detailed_placement

} err]} {

    puts "\[ERROR\] Post-repair detailed placement failed:"
    puts "$err"
    exit 1
}

check_placement


# ==============================================================================
# 24. Global Routing
# ==============================================================================

puts "\[INFO\] Running global routing..."

set route_guide "${run_dir}/route.guide"

if {[catch {

    global_route \
        -guide_file $route_guide \
        -congestion_iterations 100

} err]} {

    puts "\[ERROR\] Global routing failed:"
    puts "$err"
    exit 1
}

if {![file exists $route_guide]} {

    puts "\[ERROR\] Global routing completed but route guide was not generated."
    exit 1
}

puts "\[INFO\] Global route guide generated:"
puts "         $route_guide"


# ==============================================================================
# 25. Routing Status / Congestion Report
# ==============================================================================

puts "\[INFO\] Generating routing-status report..."

if {[catch {

    report_route_status \
        > "${run_dir}/route_status.rpt"

} err]} {

    puts "\[WARNING\] report_route_status failed:"
    puts "$err"

} else {

    puts "\[INFO\] Routing-status report generated."
}


# ==============================================================================
# 26. Detailed Routing
# ==============================================================================

puts "\[INFO\] Running detailed routing..."

if {[catch {

    detailed_route

} err]} {

    puts "\[ERROR\] Detailed routing failed:"
    puts "$err"

    # Treat routing failure as a failed dataset point.
    exit 1
}


# ==============================================================================
# 27. Final Routing Status
# ==============================================================================

puts "\[INFO\] Generating final routing-status report..."

if {[catch {

    report_route_status \
        > "${run_dir}/route_status_final.rpt"

} err]} {

    puts "\[WARNING\] Final route-status report failed:"
    puts "$err"
}


# ==============================================================================
# 28. Final Timing Analysis
# ==============================================================================

puts "\[INFO\] Running final setup timing analysis..."

if {[catch {

    report_checks \
        -path_delay max \
        -format full_clock_expanded \
        > "${run_dir}/timing_setup.rpt"

} err]} {

    puts "\[ERROR\] Setup timing report failed:"
    puts "$err"
    exit 1
}


puts "\[INFO\] Running final hold timing analysis..."

if {[catch {

    report_checks \
        -path_delay min \
        -format full_clock_expanded \
        > "${run_dir}/timing_hold.rpt"

} err]} {

    puts "\[ERROR\] Hold timing report failed:"
    puts "$err"
    exit 1
}


# ==============================================================================
# 29. Wire-Length Report
# ==============================================================================

puts "\[INFO\] Generating wire-length report..."

if {[catch {

    report_wire_length \
        > "${run_dir}/wire_length.rpt"

} err]} {

    puts "\[WARNING\] Wire-length report failed:"
    puts "$err"
}


# ==============================================================================
# 30. Final Database
# ==============================================================================

puts "\[INFO\] Saving final OpenDB database..."

if {[catch {

    write_db \
        "${run_dir}/final.odb"

} err]} {

    puts "\[ERROR\] Failed to save final database:"
    puts "$err"
    exit 1
}

if {![file exists "${run_dir}/final.odb"]} {

    puts "\[ERROR\] final.odb was not created."
    exit 1
}


# ==============================================================================
# 31. Final Summary
# ==============================================================================

puts ""
puts "=============================================================="
puts "\[SUCCESS\] OpenROAD flow completed successfully"
puts "=============================================================="
puts "Run tag          : $RUN_TAG"
puts "Array size       : $ARRAY_SIZE"
puts "Data width       : $DATA_WIDTH"
puts "Requested util   : $UTIL%"
puts "Placement density: $place_density"
puts "Clock period     : $CLK_PERIOD ns"
puts "Cell area        : $total_cell_area um^2"
puts "Core area        : $actual_core_area um^2"
puts "Projected util   : [format "%.2f" $projected_util]%"
puts ""
puts "Database         : ${run_dir}/final.odb"
puts "Route guide      : ${route_guide}"
puts "Route status     : ${run_dir}/route_status_final.rpt"
puts "Setup timing     : ${run_dir}/timing_setup.rpt"
puts "Hold timing      : ${run_dir}/timing_hold.rpt"
puts "Wire length      : ${run_dir}/wire_length.rpt"
puts "Placement report : ${run_dir}/placement.rpt"
puts "=============================================================="
