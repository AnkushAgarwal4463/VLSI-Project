set util       $::env(UTIL)
set clk_period $::env(CLK_PERIOD)
set run_tag    $::env(RUN_TAG)
set out_dir    "systolic_project/runs/$run_tag"
file mkdir $out_dir

set pdk_lib "./conda-env/share/pdk/sky130A/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib"
set pdk_lef "./conda-env/share/pdk/sky130A/libs.ref/sky130_fd_sc_hd/techlef/sky130_fd_sc_hd__nom.tlef"
set cell_lef "./conda-env/share/pdk/sky130A/libs.ref/sky130_fd_sc_hd/lef/sky130_fd_sc_hd.lef"

puts ">>> STAGE: reading LEF/LIB/netlist"
read_lef $pdk_lef
read_lef $cell_lef
read_liberty $pdk_lib
read_verilog systolic_project/synth/systolic_netlist.v
link_design systolic_array
puts ">>> STAGE: design linked OK"

create_clock -name clk -period $clk_period [get_ports clk]

puts ">>> STAGE: floorplanning"
initialize_floorplan -utilization $util -aspect_ratio 1.0 -core_space 2.0 -site unithd
make_tracks
puts ">>> STAGE: floorplan OK"

puts ">>> STAGE: pin placement"
place_pins -random -hor_layer met3 -ver_layer met2
puts ">>> STAGE: pin placement OK"

puts ">>> STAGE: global placement"
global_placement -density [expr {$util / 100.0 + 0.1}]
puts ">>> STAGE: detailed placement"
detailed_placement
check_placement
puts ">>> STAGE: placement OK"

puts ">>> STAGE: global routing"
global_route -congestion_report_file $out_dir/congestion.rpt \
             -guide_file $out_dir/route.guide
puts ">>> STAGE: global routing OK"

estimate_parasitics -placement
puts "=== TIMING (post-placement, pre-route) ==="
report_worst_slack -max
report_tns

puts ">>> STAGE: detailed routing"
detailed_route -drc_report $out_dir/drc.rpt
puts ">>> STAGE: detailed routing OK"

estimate_parasitics -global_routing
puts "=== TIMING (post-route) ==="
report_worst_slack -max
report_tns

write_def $out_dir/final.def
write_db  $out_dir/final.odb
puts "RUN COMPLETE: $run_tag"
