// Captur E-Tech BMS (LBC, part 295102091R) on the EV bus (CAN1, 500 kbit/s), as reverse engineered on the bench:
// - it stays awake only while 0x0F5 arrives every 20 ms: 7D, counter 0-F, CRC-8, FF D7 F8 00 D0
//   (CRC poly 0x1D, init 0xC4, over bytes 1, 2 and 4-8);
// - it broadcasts nothing useful: every value is read with UDS 0x22 (read-only), 29-bit IDs, request
//   0x18DADBF1, response 0x18DAF1DB, single ISO-TP frames, big-endian.
// DIDs (CanZE Zoe Ph2 field list, checked against the pack): 9007/9009 max/min cell, 9006 sum of all 68 cells
// (all 1/1024 V); 9013/9014 min/max temperature ((raw - 640) / 16 C); 9001 SOC ((raw - 300) x 0.01 %);
// 9005 pack voltage (0.1 V, informational). Current (900D) has no known scale yet and is not used.
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
    uint32_t cell_sum_mv;  // all 68 cells, as the BMS measures them
    uint32_t pack_mv;      // the series string the contactors switch: cell_sum x series / 68 (34S2P: half)
    uint32_t bms_pack_mv;  // 9005, logged only: what it measures in 34S2P is unproven
    int32_t current_ma;    // not decoded yet (900D scale unknown): always 0
    uint32_t last_ms[GRP_COUNT];   // the oldest fresh reply in each group
    bool seen[GRP_COUNT];
} pack_state_t;

extern pack_state_t g_pack;

#define CAPTUR_CELLS 68

bool captur_wants(const can_frame_t *f);                // CAN task: route to the control task?
void captur_decode(const can_frame_t *f, uint32_t rx_ms); // rx_ms: when the frame arrived, not when decoded
bool captur_fresh(uint32_t now_ms);                      // every group fresh and plausible
void captur_set_series(int cells);                       // 34 in stage 1, 68 in stage 2
bool captur_consistent(void);                            // cell sum agrees with 68 x [min, max]
void captur_tick(uint32_t now_ms);                       // keep-alive every 20 ms, one UDS read every 20 ms
uint8_t captur_crc8(const uint8_t *p, int n);            // exposed for tests
