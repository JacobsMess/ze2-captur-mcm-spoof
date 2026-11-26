// Captur E-Tech pack: what the master BMS reports on the EV bus (CAN1), and the board's requests to it.
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "can_types.h"

typedef enum { GRP_CELLS, GRP_PACK, GRP_TEMPS, GRP_COUNT } pack_group_t;

typedef struct {
    bool valid;            // every group received at least once with plausible values
    uint16_t cell_min_mv, cell_max_mv;
    int8_t temp_min_c, temp_max_c;
    float soc_pct;
    uint32_t pack_mv;
    int32_t current_ma;    // + discharge
    uint32_t last_ms[GRP_COUNT];   // time of the last plausible frame in each group
    bool seen[GRP_COUNT];
} pack_state_t;

extern pack_state_t g_pack;

bool captur_wants(const can_frame_t *f);                // CAN task: route to the control task?
void captur_decode(const can_frame_t *f, uint32_t rx_ms); // rx_ms: when the frame arrived, not when decoded
bool captur_fresh(uint32_t now_ms);                      // every group fresh and plausible
void captur_set_series(int cells);                       // 34 in stage 1, 68 in stage 2
bool captur_consistent(void);                            // pack voltage agrees with series x cell range
void captur_tick(uint32_t now_ms, bool contactors_wanted);  // sends the keep-alive / contactor request
