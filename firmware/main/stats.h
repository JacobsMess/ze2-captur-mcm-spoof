#pragma once
#include <stdint.h>
#include "can_types.h"

typedef struct {
    uint32_t rx[BUS_COUNT], tx[BUS_COUNT], tx_drop[BUS_COUNT];
    uint32_t fwd, fwd_lat_max_us, fwd_lat_sum_us;
    uint32_t fwd_lat_hist[8];       // <100, <200, <400, <800, <1600, <3200, <6400, >=6400 us
    uint32_t log_drop, gvret_bytes;
    uint32_t can_task_max_us;       // longest single pass of the CAN task
} ze2_stats_t;

extern ze2_stats_t g_stats;
void stats_reset(void);
void stats_fwd_latency(uint32_t us);
// CPU load per core in % since the last call (FreeRTOS run-time stats, idle tasks)
void stats_cpu_load(float load[2]);
