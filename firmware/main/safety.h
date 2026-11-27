// Protection ladder: steer the MCM's SOC, then float the taps so the MCM faults, then open the contactors.
#pragma once
#include <stdbool.h>
#include <stdint.h>

typedef enum { SAFE_OK, SAFE_STEER, SAFE_SOFT_TRIP, SAFE_HARD_TRIP } safe_level_t;

typedef struct {
    safe_level_t level;
    bool regen_inhibit;        // too cold to charge, or cells near full
    bool assist_inhibit;       // cells near empty
    bool taps_enabled;         // optoMOS on (MCM sees a pack): contactors verified closed, island healthy
    bool contactors_permitted; // may stay closed
    bool start_permitted;      // may start a close from open: nothing above SAFE_STEER
    const char *reason;
} safety_t;

extern safety_t g_safety;
typedef struct {
    bool ignition;          // debounced key-on
    bool key_off_seen;      // a real key-off (ignition_off_confirmed): clears the unexpected-reset latch
    bool energised;         // any contactor commanded
    bool closed;            // sequencer in CT_CLOSED (closure verified)
    const char *fault;      // local latched fault (contactor sequencer, ignition sense) or NULL: a hard trip
} safety_in_t;
void safety_tick(uint32_t now_ms, const safety_in_t *in);
// The analog island (DAC/ADC behind the ISO1540) answered recently: the NTC lines and Hall offset are under
// control. Reported by spoof_tick; false until then. Taps need it.
void safety_island_report(bool ok);
// Reset while running (brownout, watchdog, panic): the RAM latch is gone, so hard trip from boot until a real
// key-off (in practice the next power cycle).
void safety_boot_latch(const char *reason);
bool safety_ota_allowed(void);   // ignition off and contactors open; also gates CAN transmit from GVRET
