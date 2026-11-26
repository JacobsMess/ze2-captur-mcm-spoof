// Protection ladder: steer the MCM's SOC, then float the taps so the MCM faults, then open the contactors.
#pragma once
#include <stdbool.h>
#include <stdint.h>

typedef enum { SAFE_OK, SAFE_STEER, SAFE_SOFT_TRIP, SAFE_HARD_TRIP } safe_level_t;

typedef struct {
    safe_level_t level;
    bool regen_inhibit;        // too cold to charge, or cells near full
    bool assist_inhibit;       // cells near empty
    bool taps_enabled;         // optoMOS on (MCM sees a pack)
    bool contactors_permitted; // may stay closed
    bool start_permitted;      // may start a close from open: nothing above SAFE_STEER
    const char *reason;
} safety_t;

extern safety_t g_safety;
// ct_fault: the contactor sequencer's latched fault reason, or NULL. Any local fault is a hard trip.
void safety_tick(uint32_t now_ms, bool ignition, bool contactors_energised, const char *ct_fault);
bool safety_ota_allowed(void);   // ignition off and contactors open; also gates CAN transmit from GVRET
