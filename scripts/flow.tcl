# ==============================================================================
# Systolic Array OpenROAD Physical Design Flow
# ==============================================================================

# ----------------------------------------------------------------------
# 1. Read environment
# ----------------------------------------------------------------------

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

# ----------------------------------------------------------------------
# 2. Validate
# ----------------------------------------------------------------------

if {$ARRAY_SIZE <= 0} {
    puts "\[ERROR\] Invalid ARRAY_SIZE"
    exit 1
}

if {$DATA_WIDTH <= 0} {
    puts "\[ERROR\] Invalid DATA_WIDTH"
    exit 1
}

if {$UTIL <= 0 || $UTIL >= 100} {
    puts "\[ERROR\] Invalid utilization: $UTIL"
    exit 1
}

if {$CLK_PERIOD <= 0} {
    puts "\[ERROR\] Invalid clock period"
    exit 1
}

# ----------------------------------------------------------------------
# 3. Run directory
# ----------------------------------------------------------------------

set run_dir "systolic_project/runs/$RUN_TAG"

file mkdir $run_dir

puts "=============================================="
puts "SYSTOLIC ARRAY OPENROAD RUN"
puts "=============================================="
puts "ARRAY_SIZE : $ARRAY_SIZE"
puts "DATA_WIDTH : $DATA_WIDTH"
puts "UTIL       : $UTIL %"
puts "CLK_PERIOD : $CLK_PERIOD ns"
puts "RUN_TAG    : $RUN_TAG"
puts "RUN_DIR    : $run_dir"
puts "=============================================="

# ----------------------------------------------------------------------
# 4. SKY130 files
# ----------------------------------------------------------------------

set pdk_dir "./conda-env/share/pdk/sky130A"

set tech_lef \
    "${pdk_dir}/libs.ref/sky130_fd_sc_hd/techlef/sky130_fd_sc_hd__nom.tlef"

set std_cell_lef \
    "${pdk_dir}/libs.ref/sky130_fd_sc_hd/lef/sky130_fd_sc_hd.lef"

if {[info exists ::env(LIB_FILE)] && $::env(LIB_FILE) != ""} {

    set lib_file $::env(LIB_FILE)

} else {

    set lib_file \
        "${pdk_dir}/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_5v00.lib"
}

set netlist_verilog \
    "systolic_project/synth/systolic_netlist.v"

# ----------------------------------------------------------------------
# 5. Verify files
# ----------------------------------------------------------------------

foreach f [list $tech_lef $std_cell_lef $lib_file $netlist_verilog] {

    if {![file exists $f]} {

        puts "\[ERROR\] Required file not found:"
        puts "$f"

        exit 1
    }
}

# ----------------------------------------------------------------------
# 6. Read technology
# ----------------------------------------------------------------------

puts "\[INFO\] Reading technology LEF..."

read_lef -tech $tech_lef
read_lef $std_cell_lef

puts "\[INFO\] Reading Liberty..."

read_liberty $lib_file

# ----------------------------------------------------------------------
# 7. Read synthesized netlist
# ----------------------------------------------------------------------

puts "\[INFO\] Reading synthesized netlist..."

read_verilog $netlist_verilog

link_design systolic_array

# ----------------------------------------------------------------------
# 8. Create floorplan
# ----------------------------------------------------------------------

puts "\[INFO\] Calculating floorplan..."

set util_decimal [expr {$UTIL / 100.0}]

# Approximate cell area from liberty/database.
set total_cell_area 0.0

foreach inst [get_cells -hierarchical *] {

    if {![catch {get_property -quiet $inst lib_cell} cell_master]} {

        if {$cell_master != ""} {

            set area [get_property -quiet $cell_master area]

            if {$area != "" && $area > 0} {

                set total_cell_area \
                    [expr {$total_cell_area + $area}]
            }
        }
    }
}

# Fallback if OpenROAD cannot retrieve the area.
if {$total_cell_area <= 0.0} {

    set inst_count \
        [llength [get_cells -hierarchical *]]

    set average_cell_area 12.0

    set total_cell_area \
        [expr {$inst_count * $average_cell_area}]

    puts "\[WARNING\] Using estimated cell area."

}

set buffered_cell_area \
    [expr {$total_cell_area * 1.15}]

set required_core_area \
    [expr {$buffered_cell_area / $util_decimal}]

set core_dim \
    [expr {sqrt($required_core_area)}]

# SKY130 unithd site height.
set site_height 2.72

set core_dim_snapped \
    [expr {ceil($core_dim / $site_height) * $site_height}]

if {$core_dim_snapped < 150.0} {
    set core_dim_snapped 150.0
}

if {$UTIL >= 60} {

    set raw_margin 50.0

} elseif {$UTIL >= 40} {

    set raw_margin 35.0

} else {

    set raw_margin 25.0
}

set core_margin \
    [expr {ceil($raw_margin / $site_height) * $site_height}]

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

initialize_floorplan \
    -die_area "$die_x0 $die_y0 $die_x1 $die_y1" \
    -core_area "$core_x0 $core_y0 $core_x1 $core_y1" \
    -site unithd

make_tracks

# ----------------------------------------------------------------------
# 9. Clock constraints
# ----------------------------------------------------------------------

puts "\[INFO\] Creating timing constraints..."

create_clock \
    -name clk \
    -period $CLK_PERIOD \
    [get_ports clk]

set input_ports \
    [get_ports * -filter "direction == input && name != clk"]

if {[llength $input_ports] > 0} {

    set_input_delay \
        -clock clk \
        0.2 \
        $input_ports
}

set output_ports [all_outputs]

if {[llength $output_ports] > 0} {

    set_output_delay \
        -clock clk \
        0.2 \
        $output_ports
}

# ----------------------------------------------------------------------
# 10. Global placement
# ----------------------------------------------------------------------

puts "\[INFO\] Running global placement..."

set place_density [expr {$UTIL / 100.0}]

if {$place_density > 0.70} {
    set place_density 0.70
}

global_placement \
    -density $place_density

# ----------------------------------------------------------------------
# 11. Pin placement
# ----------------------------------------------------------------------

puts "\[INFO\] Placing IO pins..."

if {[catch {

    place_pins \
        -hor_layers {met3 met5} \
        -ver_layers {met2 met4}

} err]} {

    puts "\[WARNING\] Pin placement warning:"
    puts "$err"
}

# ----------------------------------------------------------------------
# 12. Detailed placement
# ----------------------------------------------------------------------

detailed_placement

check_placement

# ----------------------------------------------------------------------
# 13. Placement report
# ----------------------------------------------------------------------

if {[catch {

    report_design_area \
        > "${run_dir}/placement_area.rpt"

} err]} {

    puts "\[WARNING\] Placement area report failed:"
    puts "$err"
}

# ----------------------------------------------------------------------
# 14. Repair design
# ----------------------------------------------------------------------

if {[catch {

    repair_design

} err]} {

    puts "\[WARNING\] repair_design failed:"
    puts "$err"
}

if {[catch {

    repair_timing \
        -setup \
        -setup_margin 0.2

} err]} {

    puts "\[WARNING\] repair_timing failed:"
    puts "$err"
}

detailed_placement

check_placement

# ----------------------------------------------------------------------
# 15. Global routing
# ----------------------------------------------------------------------

puts "\[INFO\] Running global routing..."

set route_guide \
    "${run_dir}/route.guide"

set congestion_report \
    "${run_dir}/congestion.rpt"

global_route \
    -guide_file $route_guide \
    -congestion_report_file $congestion_report \
    -congestion_iterations 100

if {![file exists $route_guide]} {

    puts "\[ERROR\] route.guide was not generated."

    exit 1
}

if {![file exists $congestion_report]} {

    puts "\[WARNING\] congestion.rpt was not generated."

}

# ----------------------------------------------------------------------
# 16. Global-route wirelength
# ----------------------------------------------------------------------

puts "\[INFO\] Measuring global-route wirelength..."

if {[catch {

    report_wire_length \
        -global_route \
        -summary \
        -file "${run_dir}/wirelength_global.rpt"

} err]} {

    puts "\[WARNING\] Global-route wirelength report failed:"
    puts "$err"
}

# ----------------------------------------------------------------------
# 17. Detailed routing
# ----------------------------------------------------------------------

puts "\[INFO\] Running detailed routing..."

detailed_route

# ----------------------------------------------------------------------
# 18. Detailed-route wirelength
# ----------------------------------------------------------------------

puts "\[INFO\] Measuring detailed-route wirelength..."

if {[catch {

    report_wire_length \
        -detailed_route \
        -summary \
        -file "${run_dir}/wirelength_detailed.rpt"

} err]} {

    puts "\[WARNING\] Detailed-route wirelength report failed:"
    puts "$err"
}

# ----------------------------------------------------------------------
# 19. Combined wirelength report
# ----------------------------------------------------------------------

if {[catch {

    report_wire_length \
        -detailed_route \
        -file "${run_dir}/wirelength_final.rpt"

} err]} {

    puts "\[WARNING\] Final wirelength report failed:"
    puts "$err"
}

# ----------------------------------------------------------------------
# 20. Routing status
# ----------------------------------------------------------------------

if {[catch {

    report_route_status \
        > "${run_dir}/route_status_final.rpt"

} err]} {

    puts "\[WARNING\] Route status report failed:"
    puts "$err"
}

# ----------------------------------------------------------------------
# 21. Timing reports
# ----------------------------------------------------------------------

puts "\[INFO\] Generating setup timing report..."

if {[catch {

    report_checks \
        -path_delay max \
        -format full_clock_expanded \
        > "${run_dir}/timing_setup.rpt"

} err]} {

    puts "\[WARNING\] Setup timing report failed:"
    puts "$err"
}

puts "\[INFO\] Generating hold timing report..."

if {[catch {

    report_checks \
        -path_delay min \
        -format full_clock_expanded \
        > "${run_dir}/timing_hold.rpt"

} err]} {

    puts "\[WARNING\] Hold timing report failed:"
    puts "$err"
}

# ----------------------------------------------------------------------
# 22. Final database
# ----------------------------------------------------------------------

puts "\[INFO\] Saving final database..."

write_db \
    "${run_dir}/final.odb"

if {![file exists "${run_dir}/final.odb"]} {

    puts "\[ERROR\] final.odb was not created."

    exit 1
}

# ----------------------------------------------------------------------
# 23. Final summary
# ----------------------------------------------------------------------

puts ""
puts "=============================================="
puts "OPENROAD FLOW COMPLETED"
puts "=============================================="
puts "Run tag: $RUN_TAG"
puts ""
puts "Generated:"
puts "  final.odb"
puts "  route.guide"
puts "  congestion.rpt"
puts "  wirelength_global.rpt"
puts "  wirelength_detailed.rpt"
puts "  wirelength_final.rpt"
puts "  route_status_final.rpt"
puts "  timing_setup.rpt"
puts "  timing_hold.rpt"
puts "=============================================="
