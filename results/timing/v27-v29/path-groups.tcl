puts "DATA REQUEST"
report_checks -through [get_pins memory_system/d_valid] -path_delay max -group_path_count 1 -digits 4
puts "I CACHE RETURN"
report_checks -through [get_pins memory_system/split.icache/u_rsp_valid] -path_delay max -group_path_count 1 -digits 4
puts "D CACHE RETURN"
report_checks -through [get_pins memory_system/split.dcache/u_rsp_valid] -path_delay max -group_path_count 1 -digits 4
puts "MEMORY REQUEST OUTPUT"
report_checks -to [get_ports {req_valid req_addr*}] -path_delay max -group_path_count 1 -digits 4
puts "REGISTER TO REGISTER"
report_checks -from [all_registers -output_pins] -to [all_registers -data_pins] -path_delay max -group_path_count 1 -digits 4
