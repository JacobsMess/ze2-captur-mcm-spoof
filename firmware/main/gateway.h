// IMA bus man-in-the-middle. BYPASS: K4 relaxed, the IMA bus is one piece and both CAN controllers just listen.
// SPLIT: K4 energised, CAN2 (MCM side) and CAN3 (PCM side) are separate buses and every frame is forwarded
// to the other side, through the rewrite hooks. ARMING: both controllers asked for normal mode; K4 is energised
// only once both confirm it. Falls back to BYPASS (latched until key-off) if a controller doesn't confirm in
// time, leaves normal mode, or either half goes quiet while split. A hung CPU is reset by the task watchdog
// (main.c), which releases RELAY_SPLIT, so K4 drops back to bypass.
#pragma once
#include <stdbool.h>
#include "can_types.h"

typedef enum { GW_BYPASS, GW_SPLIT, GW_FAILED, GW_ARMING } gw_state_t;

// a rewrite hook may edit the frame in place; return false to drop it
typedef bool (*gw_hook_t)(bus_id_t from, can_frame_t *f);

void gateway_init(void);
void gateway_on_frame(const can_frame_t *f);      // CAN task
bool gateway_wants(const can_frame_t *f);         // frames the control task decodes (Honda SOC etc.)
void gateway_tick(uint32_t now_ms, bool allow_split);  // control task, 100 Hz
gw_state_t gateway_state(void);
bool gateway_add_hook(uint32_t id, gw_hook_t hook);

// Honda side as seen by the gateway (decoded on the control task)
typedef struct {
    bool valid;
    float mcm_soc_pct;     // what the MCM believes (TODO: ID/scale from logs)
    uint32_t last_ms;
} honda_state_t;
extern honda_state_t g_honda;
void gateway_decode(const can_frame_t *f, uint32_t now_ms);  // control task
