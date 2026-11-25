#include "stats.h"

#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mcp2515.h"

ze2_stats_t g_stats;

void stats_reset(void)
{
    memset(&g_stats, 0, sizeof(g_stats));
    mcp_stats_reset();
}

void stats_fwd_latency(uint32_t us)
{
    g_stats.fwd++;
    g_stats.fwd_lat_sum_us += us;
    if (us > g_stats.fwd_lat_max_us) g_stats.fwd_lat_max_us = us;
    int b = 0;
    for (uint32_t lim = 100; b < 7 && us >= lim; lim <<= 1) b++;
    g_stats.fwd_lat_hist[b]++;
}

void stats_cpu_load(float load[2])
{
    static uint32_t last_total, last_idle[2];
    UBaseType_t n = uxTaskGetNumberOfTasks();
    TaskStatus_t *ts = pvPortMalloc(sizeof(TaskStatus_t) * (n + 4));
    if (!ts) return;
    configRUN_TIME_COUNTER_TYPE total = 0;
    n = uxTaskGetSystemState(ts, n + 4, &total);
    uint32_t idle[2] = {0, 0};
    for (UBaseType_t i = 0; i < n; i++) {
        if (strcmp(ts[i].pcTaskName, "IDLE0") == 0) idle[0] = ts[i].ulRunTimeCounter;
        if (strcmp(ts[i].pcTaskName, "IDLE1") == 0) idle[1] = ts[i].ulRunTimeCounter;
    }
    vPortFree(ts);
    uint32_t dt = (uint32_t)total - last_total;   // run-time counter is per core wall time (us)
    for (int c = 0; c < 2; c++) {
        uint32_t di = idle[c] - last_idle[c];
        load[c] = dt ? 100.0f * (1.0f - (float)di / (float)dt) : 0;
        if (load[c] < 0) load[c] = 0;
        last_idle[c] = idle[c];
    }
    last_total = (uint32_t)total;
}
