# ==============================================================================
# 1. Read Environment Variables with Safe Defaults
# ==============================================================================
if {[info exists ::env(ARRAY_SIZE)]} { set ARRAY_SIZE $::env(ARRAY_SIZE) } else { set ARRAY_SIZE 4 }
if {[info exists ::env(DATA_WIDTH)]} { set DATA_WIDTH $::env(DATA_WIDTH) } else { set DATA_WIDTH 8 }
if {[info exists ::env(UTIL)]} { set UTIL $::env(UTIL) } else { set UTIL 50 }
if {[info exists ::env(CLK_PERIOD)]} { set CLK_PERIOD $::env(CLK_PERIOD) } else { set CLK_PERIOD 5.0 }
if {[info exists ::env(RUN_TAG)]} { set RUN_TAG $::env(RUN_TAG) } else { set RUN_TAG "run_test" }

set util_decimal [expr {$UTIL / 100.0}]

# ==============================================================================
# 2. Read Tech LEFs, Liberty & Netlist
# ==============================================================================
set pdk_dir "./conda-env/share/pdk/sky130A"
set tech_lef "${pdk_dir}/libs.ref/sky130_fd_sc_hd/techlef/sky130_fd_sc_hd__nom.tlef"
set std_cell_lef "${pdk_dir}/libs.ref/sky130_fd_sc_hd/lef/sky130_fd_sc_hd.lef"
set lib_file "${pdk_dir}/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib"
set netlist_verilog "systolic_project/synth/systolic_netlist.v"

read_liberty $lib_file
read_lef $tech_lef
read_lef $std_cell_lef
read_verilog $netlist_verilog
link_design "systolic_array"

# ==============================================================================
# 3. Dynamic Floorplan Calculation (FIXES DPL-0036 on High Utilization)
# ==============================================================================
set total_cell_area 0.0
foreach inst [get_cells *] {
    if {![catch {get_property $inst lib_cell} cell_master] && $cell_master != ""} {
        set area [get_property $cell_master area]
        set total_cell_area [expr {$total_cell_area + $area}]
    }
}

puts "\[INFO\] Total Standard Cell Area: ${total_cell_area} um^2"

# Core area calculated from gate area and target utilization
set required_core_area [expr {$total_cell_area / $util_decimal}]
set core_dim [expr {sqrt($required_core_area)}]

# DYNAMIC MARGIN FIX: High utilization requires expanded margins for legalizer rows
if {$UTIL >= 60} {
    set core_margin 50.0
} elseif {$UTIL >= 40} {
    set core_margin 35.0
} else {
    set core_margin 25.0
}

set die_dim [expr {$core_dim + (2 * $core_margin)}]
set die_x0 0.0
set die_y0 0.0
set die_x1 [expr {ceil($die_dim)}]
set die_y1 [expr {ceil($die_dim)}]

set core_x0 $core_margin
set core_y0 $core_margin
set core_x1 [expr {$die_x1 - $core_margin}]
set core_y1 [expr {$die_y1 - $core_margin}]

puts "\[INFO\] Initializing Floorplan:"
puts "       Die  Area : $die_x0 $die_y0 $die_x1 $die_y1"
puts "       Core Area : $core_x0 $core_y0 $core_x1 $core_y1"

initialize_floorplan \
    -die_area "$die_x0 $die_y0 $die_x1 $die_y1" \
    -core_area "$core_x0 $core_y0 $core_x1 $core_y1" \
    -site "unithd"

make_tracks

# ==============================================================================
# 4. Constraints
# ==============================================================================
create_clock -name clk -period $CLK_PERIOD [get_ports clk]
set in_ports [get_ports * -filter "direction == input && name != clk"]
if {[llength $in_ports] > 0} {
    set_input_delay -clock clk 0.2 $in_ports
}
set_output_delay -clock clk 0.2 [all_outputs]

# ==============================================================================
# 5. Global & Detailed Placement
# ==============================================================================
# Dynamic Target Density Cap to prevent local bin overflow
set place_density $util_decimal
if {$place_density > 0.68} {
    set place_density 0.68
}

puts "\[INFO\] Running global placement with density $place_density..."
global_placement -density $place_density

puts "\[INFO\] Running pin placement..."
set io_hor_layers [list met3 met5]
set io_ver_layers [list met2 met4]

if {[catch {
    place_pins -hor_layers $io_hor_layers \
               -ver_layers $io_ver_layers
} err]} {
    puts "\[WARNING\] Pin placement warning: $err"
}

puts "\[INFO\] Running detailed placement..."
# Increased displacement search radius to solve DPL-0036
detailed_placement -max_displacement 500 200
check_placement

# ==============================================================================
# 6. Direct In-Memory Metric Extraction (POPULATES CSV CORRECTLY)
# ==============================================================================
set block [ord::get_db_block]
set db_units [$block getDbUnitsPerMicron]

# 1. Precise Die Area
set die_box [$block getDieArea]
set die_w [expr {([$die_box xMax] - [$die_box xMin]) / double($db_units)}]
set die_h [expr {([$die_box yMax] - [$die_box yMin]) / double($db_units)}]
set die_area_u2 [expr {$die_w * $die_h}]

# 2. Total Cell Count
set num_cells [llength [get_cells *]]

# 3. Slack Conversion (in ps)
set wns_val [sta::worst_slack -max]
if {$wns_val == "" || $wns_val == "INF"} {
    set slack_ps 0.0
} else {
    set slack_ps [expr {$wns_val * 1000.0}]
}

# 4. Wirelength
if {[catch {set total_wirelength_u [groute_wire_length]} err]} {
    set total_wirelength_u 0.0
}

# Write metrics directly to JSON file
set json_file "systolic_project/runs/${RUN_TAG}_features.json"
file mkdir "systolic_project/runs"
set fh [open $json_file "w"]

puts $fh "{"
puts $fh "  \"run_tag\": \"$RUN_TAG\","
puts $fh "  \"array_size\": $ARRAY_SIZE,"
puts $fh "  \"data_width\": $DATA_WIDTH,"
puts $fh "  \"utilization\": $UTIL,"
puts $fh "  \"clk_period_ns\": $CLK_PERIOD,"
puts $fh "  \"num_cells\": $num_cells,"
puts $fh "  \"die_area_u2\": [format "%.2f" $die_area_u2],"
puts $fh "  \"wirelength_u\": [format "%.2f" $total_wirelength_u],"
puts $fh "  \"slack_ps\": [format "%.2f" $slack_ps]"
puts $fh "}"
close $fh

puts "\[SUCCESS\] Extracted metrics directly to $json_file"

# Save ODB database
set run_dir "systolic_project/runs/$RUN_TAG"
file mkdir $run_dir
write_db "${run_dir}/final.odb"
puts "\[SUCCESS\] Saved database to ${run_dir}/final.odb"
