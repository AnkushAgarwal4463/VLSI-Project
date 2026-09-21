# ==============================================================================
# 1. Read Environment Variables with Sweep Defaults
# ==============================================================================
if {[info exists ::env(UTIL)] && $::env(UTIL) != ""} {
    set UTIL $::env(UTIL)
} else {
    set UTIL 50
}

if {[info exists ::env(CLK_PERIOD)] && $::env(CLK_PERIOD) != ""} {
    set CLK_PERIOD $::env(CLK_PERIOD)
} else {
    set CLK_PERIOD 5.0
}

if {[info exists ::env(SITE)] && $::env(SITE) != ""} {
    set site_name $::env(SITE)
} else {
    set site_name "unithd"
}

# Convert utilization percentage to decimal (e.g., 70 -> 0.70)
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
# 3. Dynamic Floorplan Calculation with Safety Buffer
# ==============================================================================
# Compute total standard cell area from netlist in um^2
set total_cell_area 0.0
foreach inst [get_cells *] {
    set cell_master [get_property $inst lib_cell]
    if {$cell_master != ""} {
        set area [get_property $cell_master area]
        set total_cell_area [expr {$total_cell_area + $area}]
    }
}

puts "\[INFO\] Total Standard Cell Area: ${total_cell_area} um^2"

# Apply a 1.08x safety buffer (8% extra core room) to absorb cell padding & site alignment loss
set area_buffer 1.08
set buffered_cell_area [expr {$total_cell_area * $area_buffer}]

# Calculate required core area based on target utilization
set required_core_area [expr {$buffered_cell_area / $util_decimal}]

# Calculate core dimensions (square aspect ratio)
set core_dim [expr {sqrt($required_core_area)}]

# Set margin for I/O pins and power routing (scaled up for high-pin count/utilization)
if {$UTIL >= 60} {
    set core_margin 45.0
} else {
    set core_margin 30.0
}

# Calculate total die dimensions
set die_dim [expr {$core_dim + (2 * $core_margin)}]

set die_x0 0.0
set die_y0 0.0
set die_x1 [expr {ceil($die_dim)}]
set die_y1 [expr {ceil($die_dim)}]

set core_x0 $core_margin
set core_y0 $core_margin
set core_x1 [expr {$die_x1 - $core_margin}]
set core_y1 [expr {$die_y1 - $core_margin}]

puts "\[INFO\] Dynamic Floorplan Sizing (with 8% safety buffer):"
puts "       Die  Area : $die_x0 $die_y0 $die_x1 $die_y1"
puts "       Core Area : $core_x0 $core_y0 $core_x1 $core_y1"

initialize_floorplan \
    -die_area "$die_x0 $die_y0 $die_x1 $die_y1" \
    -core_area "$core_x0 $core_y0 $core_x1 $core_y1" \
    -site $site_name

make_tracks

# ==============================================================================
# 4. Timing Constraints
# ==============================================================================
create_clock -name clk -period $CLK_PERIOD [get_ports clk]
set in_ports [get_ports * -filter "direction == input && name != clk"]
if {[llength $in_ports] > 0} {
    set_input_delay -clock clk 0.2 $in_ports
}
set_output_delay -clock clk 0.2 [all_outputs]

# ==============================================================================
# 5. Global & Detailed Placement with Safe Density Cap
# ==============================================================================
# Since floorplan is sized with a safety buffer, set placement density slightly above 
# target utilization, capped at 0.78 so detailed placement always succeeds
set place_density [expr {$util_decimal + 0.03}]
if {$place_density > 0.78} {
    set place_density 0.78
}

puts "\[INFO\] Running global placement with target density: ${place_density}..."

# Apply global placement padding for high utilization runs
if {$UTIL >= 60} {
    set_placement_padding -global -left 1 -right 1
}

global_placement -density $place_density

puts "\[INFO\] Running multi-layer pin placement..."
set io_hor_layers [list met3 met5]
set io_ver_layers [list met2 met4]

if {[catch {
    place_pins -hor_layers $io_hor_layers \
               -ver_layers $io_ver_layers
} err]} {
    puts "\[WARNING\] Pin placement failed: $err"
}

puts "\[INFO\] Running detailed placement..."
# Increased max_displacement to give legalizer room to resolve dense regions
detailed_placement -max_displacement 300 100
check_placement

# ==============================================================================
# 6. Save Database
# ==============================================================================
if {[info exists ::env(RUN_TAG)] && $::env(RUN_TAG) != ""} {
    set run_dir "systolic_project/runs/$::env(RUN_TAG)"
} else {
    set run_dir "systolic_project/runs/sweep_run"
}

file mkdir $run_dir
write_db "${run_dir}/final.odb"
puts "\[INFO\] Successfully saved database to ${run_dir}/final.odb"
