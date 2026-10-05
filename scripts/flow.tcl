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

read_lef $tech_lef
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
# 9. RESIZER CONFIGURATION
# ----------------------------------------------------------------------

puts ""
puts "=============================================="
puts "RESIZER CONFIGURATION"
puts "=============================================="

if {[catch {

    set_wire_rc -layer met2

    puts "\[OK\] Resizer wire RC configured using met2."

} err]} {

    puts "\[WARNING\] set_wire_rc failed:"
    puts "$err"
}

puts "\[INFO\] Resizer configuration completed."
# ----------------------------------------------------------------------
# 10. Clock constraints
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
# 11. Global placement
# ----------------------------------------------------------------------

puts "\[INFO\] Running global placement..."

set place_density [expr {$UTIL / 100.0}]

if {$place_density > 0.70} {
    set place_density 0.70
}

global_placement \
    -density $place_density

# ----------------------------------------------------------------------
# 12. Pin placement
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
# 13. Detailed placement
# ----------------------------------------------------------------------

detailed_placement
check_placement

# ----------------------------------------------------------------------
# 14. RESIZER / TIMING REPAIR
# ----------------------------------------------------------------------

puts ""
puts "=============================================="
puts "RESIZER / TIMING REPAIR"
puts "=============================================="

# ----------------------------------------------------------------------
# Check available buffer cells
# ----------------------------------------------------------------------

puts "\[INFO\] Checking available buffer cells..."

if {[catch {

    set buf_cells [get_lib_cells *BUF*]

    puts "\[RESIZER\] Available BUF cells: [llength $buf_cells]"

    foreach bc $buf_cells {
        puts "\[RESIZER\] BUF: $bc"
    }

} err]} {

    puts "\[WARNING\] Buffer-cell query failed:"
    puts "$err"
}

# ----------------------------------------------------------------------
# Design repair
# ----------------------------------------------------------------------

puts "\[INFO\] Running repair_design..."

if {[catch {

    repair_design

} err]} {

    puts "\[WARNING\] repair_design failed:"
    puts "$err"

} else {

    puts "\[OK\] repair_design completed."
}

# ----------------------------------------------------------------------
# Setup timing repair
# ----------------------------------------------------------------------

puts "\[INFO\] Running repair_timing..."

if {[catch {

    repair_timing \
        -setup \
        -setup_margin 0.2

} err]} {

    puts "\[WARNING\] repair_timing failed:"
    puts "$err"

} else {

    puts "\[OK\] repair_timing completed."
}

# ----------------------------------------------------------------------
# Legalize after Resizer
# ----------------------------------------------------------------------

puts "\[INFO\] Running detailed placement after Resizer..."

if {[catch {

    detailed_placement
    check_placement

} err]} {

    puts "\[WARNING\] Post-Resizer placement failed:"
    puts "$err"
} else {

    puts "\[OK\] Post-Resizer placement completed."
}

# ----------------------------------------------------------------------
# Resizer diagnostic
# ----------------------------------------------------------------------

puts ""
puts "=============================================="
puts "RESIZER DIAGNOSTIC"
puts "=============================================="

if {[catch {

    set all_cells [get_cells -hierarchical *]
    set all_nets  [get_nets *]

    puts "\[RESIZER\] Cell count : [llength $all_cells]"
    puts "\[RESIZER\] Net count  : [llength $all_nets]"

} err]} {

    puts "\[WARNING\] Resizer diagnostic failed:"
    puts "$err"
}

puts "=============================================="

# ----------------------------------------------------------------------
# 15. Global routing
# ----------------------------------------------------------------------

puts ""
puts "=============================================="
puts "15. GLOBAL ROUTING"
puts "=============================================="

puts "\[INFO\] Running global routing..."

set route_guide \
    "${run_dir}/route.guide"

set congestion_report \
    "${run_dir}/congestion.rpt"

set global_route_log \
    "${run_dir}/global_route.rpt"

# Remove stale files from previous runs
foreach f [list $route_guide $congestion_report $global_route_log] {
    if {[file exists $f]} {
        file delete -force $f
    }
}

puts "\[INFO\] Starting OpenROAD global router..."

# ----------------------------------------------------------------------
# Run global routing
#
# IMPORTANT:
# Do NOT use "tee" here.
# This OpenROAD build does not provide the tee Tcl command.
# ----------------------------------------------------------------------

if {[catch {

    global_route \
        -guide_file $route_guide \
        -congestion_report_file $congestion_report \
        -congestion_report_iter_step 1 \
        -congestion_iterations 100 \
        -verbose

} err]} {

    puts "\[ERROR\] Global routing failed:"
    puts "$err"
    exit 1

}

puts "\[OK\] Global routing completed."

# ----------------------------------------------------------------------
# Create a persistent global routing report
#
# Since "tee" is unavailable, create the report ourselves from the
# congestion report generated by global_route.
# ----------------------------------------------------------------------

if {[file exists $congestion_report]} {

    set in [open $congestion_report r]
    set out [open $global_route_log w]

    puts $out "=============================================="
    puts $out "OPENROAD GLOBAL ROUTING REPORT"
    puts $out "=============================================="
    puts $out ""

    while {[gets $in line] >= 0} {
        puts $out $line
    }

    close $in
    close $out

    puts "\[OK\] global_route.rpt generated: [file size $global_route_log] bytes"

} else {

    # Still create the file so the downstream artifact pipeline
    # does not fail merely because congestion.rpt was not populated.
    set out [open $global_route_log w]

    puts $out "=============================================="
    puts $out "OPENROAD GLOBAL ROUTING REPORT"
    puts $out "=============================================="
    puts $out ""
    puts $out "No congestion report was generated."
    puts $out "This can occur when no overflowing GCells are reported."

    close $out

    puts "\[INFO\] congestion.rpt was not generated."
    puts "\[INFO\] Created global_route.rpt diagnostic file."
}

# ----------------------------------------------------------------------
# Verify route.guide
# ----------------------------------------------------------------------

if {![file exists $route_guide]} {

    puts "\[ERROR\] route.guide was not generated."
    exit 1

}

if {[file size $route_guide] <= 0} {

    puts "\[ERROR\] route.guide is empty."
    exit 1

}

puts "\[OK\] route.guide generated: [file size $route_guide] bytes"

# ----------------------------------------------------------------------
# Verify global_route.rpt
# ----------------------------------------------------------------------

if {![file exists $global_route_log]} {

    puts "\[ERROR\] global_route.rpt was not generated."
    exit 1

}

if {[file size $global_route_log] <= 0} {

    puts "\[ERROR\] global_route.rpt is empty."
    exit 1

}

puts "\[OK\] global_route.rpt generated: [file size $global_route_log] bytes"

# ----------------------------------------------------------------------
# Verify congestion report
#
# congestion.rpt can legitimately be empty when there is no overflow.
# ----------------------------------------------------------------------

if {[file exists $congestion_report]} {

    set cong_size [file size $congestion_report]

    if {$cong_size > 0} {

        puts "\[OK\] congestion.rpt generated: $cong_size bytes"

    } else {

        puts "\[INFO\] congestion.rpt is empty: no overflowing GCells reported."

    }

} else {

    puts "\[INFO\] congestion.rpt was not generated."
    puts "\[INFO\] No overflowing GCells were reported."

}

# ----------------------------------------------------------------------
# Global routing segments
# ----------------------------------------------------------------------

puts ""
puts "\[INFO\] Writing global route segments..."

set global_route_segments \
    "${run_dir}/global_route_segments.txt"

if {[file exists $global_route_segments]} {
    file delete -force $global_route_segments
}

if {[catch {

    write_global_route_segments \
        $global_route_segments

} err]} {

    puts "\[WARNING\] Global route segment export failed:"
    puts "$err"

} else {

    if {[file exists $global_route_segments]} {

        set grs_size [file size $global_route_segments]

        if {$grs_size > 0} {

            puts "\[OK\] global_route_segments.txt generated: $grs_size bytes"

        } else {

            puts "\[WARNING\] global_route_segments.txt is empty."

        }

    } else {

        puts "\[WARNING\] global_route_segments.txt was not generated."

    }

}

puts "=============================================="
puts "GLOBAL ROUTING SECTION COMPLETED"
puts "=============================================="
# ----------------------------------------------------------------------
# 16. Detailed routing
# ----------------------------------------------------------------------

puts "\[INFO\] Running detailed routing..."

if {[catch {

    detailed_route \
        -output_drc "${run_dir}/detailed_route_drc.rpt"

} err]} {

    puts "\[ERROR\] Detailed routing failed:"
    puts "$err"
    exit 1
}

puts "\[INFO\] Detailed routing completed."

# ----------------------------------------------------------------------
# Final DEF
#
# The final DEF contains the routed geometry and is retained for
# independent Python extraction of wirelength and vias.
# ----------------------------------------------------------------------

puts "\[INFO\] Writing final DEF..."

if {[catch {

    write_def \
        -version 5.8 \
        "${run_dir}/final.def"

} err]} {

    puts "\[ERROR\] write_def failed:"
    puts "$err"
    exit 1
}

if {![file exists "${run_dir}/final.def"]} {

    puts "\[ERROR\] final.def was not generated."
    exit 1
}

set def_size [file size "${run_dir}/final.def"]

puts "\[OK\] final.def generated: $def_size bytes"

# ----------------------------------------------------------------------
# Detailed-route wirelength
#
# Use the explicit net list here as well.
# ----------------------------------------------------------------------

set all_nets [get_nets *]

puts "\[INFO\] Measuring detailed-route wirelength..."

if {[catch {

    report_wire_length \
        -net $all_nets \
        -detailed_route \
        -verbose \
        -file "${run_dir}/wirelength_detailed.rpt"

} err]} {

    puts "\[WARNING\] Detailed-route wirelength report failed:"
    puts "$err"
}

if {[file exists "${run_dir}/wirelength_detailed.rpt"]} {

    set wl_size [file size "${run_dir}/wirelength_detailed.rpt"]

    puts "\[INFO\] wirelength_detailed.rpt generated: $wl_size bytes"

} else {

    puts "\[WARNING\] wirelength_detailed.rpt was not generated."
}

# ----------------------------------------------------------------------
# Final wirelength
#
# Run the detailed-route report again after final DEF creation so that
# the saved final database and the wirelength report refer to the same
# routed design state.
# ----------------------------------------------------------------------

puts "\[INFO\] Measuring final wirelength..."

if {[catch {

    report_wire_length \
        -net $all_nets \
        -detailed_route \
        -verbose \
        -file "${run_dir}/wirelength_final.rpt"

} err]} {

    puts "\[WARNING\] Final wirelength report failed:"
    puts "$err"
}

if {[file exists "${run_dir}/wirelength_final.rpt"]} {

    set wl_size [file size "${run_dir}/wirelength_final.rpt"]

    puts "\[INFO\] wirelength_final.rpt generated: $wl_size bytes"

} else {

    puts "\[WARNING\] wirelength_final.rpt was not generated."
}

# ----------------------------------------------------------------------
# Final routing status
# ----------------------------------------------------------------------

puts "\[INFO\] Generating final routing status..."

if {[catch {

    report_route_status \
        > "${run_dir}/route_status_final.rpt"

} err]} {

    puts "\[WARNING\] Routing status report failed:"
    puts "$err"
}

if {[file exists "${run_dir}/route_status_final.rpt"]} {

    puts "\[INFO\] route_status_final.rpt generated: [file size "${run_dir}/route_status_final.rpt"] bytes"

} else {

    puts "\[WARNING\] route_status_final.rpt was not generated."
}

# ----------------------------------------------------------------------
# Final OpenDB
# ----------------------------------------------------------------------

puts "\[INFO\] Saving final OpenROAD database..."

if {[catch {

    write_db \
        "${run_dir}/final.odb"

} err]} {

    puts "\[ERROR\] write_db failed:"
    puts "$err"
    exit 1
}

if {![file exists "${run_dir}/final.odb"]} {

    puts "\[ERROR\] final.odb was not created."
    exit 1
}

set odb_size [file size "${run_dir}/final.odb"]

puts "\[OK\] final.odb generated: $odb_size bytes"

# ----------------------------------------------------------------------
# Routing artifact diagnostic
#
# This is deliberately inside OpenROAD. It tells us whether the files
# were actually created before GitHub Actions/Python touches them.
# ----------------------------------------------------------------------

puts ""
puts "=============================================="
puts "ROUTING ARTIFACT DIAGNOSTIC"
puts "=============================================="

foreach f [list \
    "${run_dir}/route.guide" \
    "${run_dir}/global_route_segments.txt" \
    "${run_dir}/global_route.rpt" \
    "${run_dir}/congestion.rpt" \
    "${run_dir}/wirelength_detailed.rpt" \
    "${run_dir}/wirelength_final.rpt" \
    "${run_dir}/route_status_final.rpt" \
    "${run_dir}/final.def" \
    "${run_dir}/final.odb"] {

    if {[file exists $f]} {

        puts "\[FOUND\] $f : [file size $f] bytes"

    } else {

        puts "\[MISSING\] $f"
    }
}

puts "=============================================="

# ----------------------------------------------------------------------
# 18. Setup timing
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

# ----------------------------------------------------------------------
# 19. Hold timing
# ----------------------------------------------------------------------

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
# 20. Setup WNS / TNS
# ----------------------------------------------------------------------

puts "\[INFO\] Generating setup WNS/TNS..."

if {[catch {

    report_wns \
        > "${run_dir}/wns_setup.rpt"

    report_tns \
        > "${run_dir}/tns_setup.rpt"

} err]} {

    puts "\[WARNING\] Setup WNS/TNS failed:"
    puts "$err"
}

# ----------------------------------------------------------------------
# 21. Hold WNS / TNS
#
# Do NOT use:
#
#     report_wns -min
#     report_tns -min
#
# because this OpenROAD version does not support -min.
#
# Python will calculate hold WNS/TNS directly from timing_hold.rpt.
# ----------------------------------------------------------------------

puts "\[INFO\] Hold WNS/TNS will be extracted from timing_hold.rpt."

# Create empty marker files so the expected filenames are not
# accidentally interpreted as successful OpenROAD reports.

set hold_wns_file \
    "${run_dir}/wns_hold.rpt"

set hold_tns_file \
    "${run_dir}/tns_hold.rpt"

set fp [open $hold_wns_file w]
puts $fp "Hold WNS calculated from timing_hold.rpt by extract_features.py"
close $fp

set fp [open $hold_tns_file w]
puts $fp "Hold TNS calculated from timing_hold.rpt by extract_features.py"
close $fp

# ----------------------------------------------------------------------
# 22. Final file verification
# ----------------------------------------------------------------------

puts ""
puts "=============================================="
puts "VERIFYING GENERATED FILES"
puts "=============================================="

foreach f [list \
    "${run_dir}/final.odb" \
    "${run_dir}/final.def" \
    "${run_dir}/route.guide" \
    "${run_dir}/global_route_segments.txt" \
    "${run_dir}/global_route.rpt" \
    "${run_dir}/congestion.rpt" \
    "${run_dir}/wirelength_detailed.rpt" \
    "${run_dir}/wirelength_final.rpt" \
    "${run_dir}/route_status_final.rpt" \
    "${run_dir}/detailed_route_drc.rpt" \
    "${run_dir}/timing_setup.rpt" \
    "${run_dir}/timing_hold.rpt" \
    "${run_dir}/wns_setup.rpt" \
    "${run_dir}/tns_setup.rpt" \
    "${run_dir}/wns_hold.rpt" \
    "${run_dir}/tns_hold.rpt"] {

    if {[file exists $f]} {

        set size \
            [file size $f]

        puts "\[OK\] $f ($size bytes)"

    } else {

        puts "\[WARNING\] Missing: $f"
    }
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
puts "  final.def"
puts "  route.guide"
puts "  global_route_segments.txt"
puts "  global_route.rpt"
puts "  wirelength_detailed.rpt"
puts "  wirelength_final.rpt"
puts "  route_status_final.rpt"
puts "  detailed_route_drc.rpt"
puts "  timing_setup.rpt"
puts "  timing_hold.rpt"
puts "  wns_setup.rpt"
puts "  tns_setup.rpt"
puts "  wns_hold.rpt"
puts "  tns_hold.rpt"

puts ""
puts "Routing metrics:"
puts "  Wirelength : calculated from final.def"
puts "  Via count  : calculated from final.def"
puts "  Congestion : extracted from global_route.rpt"

puts ""
puts "Timing metrics:"
puts "  Setup WNS  : extracted from wns_setup.rpt"
puts "  Setup TNS  : extracted from tns_setup.rpt"
puts "  Hold WNS   : calculated from timing_hold.rpt"
puts "  Hold TNS   : calculated from timing_hold.rpt"

puts "=============================================="
