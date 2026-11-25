// Frame layout follows the common SimpBMS/Victron-style BMS messages (0x351 limits, 0x355 SOC, 0x356 V/I/T)
// that ZombieVerter can take as a BMS. CHECK against the ZombieVerter firmware version in use before stage 2.
#include "zombie.h"

#include "can_types.h"
#include "captur.h"
#include "config.h"
#include "safety.h"

static void put16(uint8_t *p, int v) { p[0] = v; p[1] = v >> 8; }

void zombie_tick(uint32_t now_ms, bool stage2)
{
    static uint32_t last;
    if (!stage2 || now_ms - last < 100) return;
    last = now_ms;
    const pack_state_t *p = &g_pack;
    // stale data or any trip: advertise zero charge and discharge current, so the VCU stops using the pack
    bool ok = captur_fresh(now_ms) && g_safety.level < SAFE_SOFT_TRIP;
    can_frame_t f = {.dlc = 8};

    f.id = 0x351;   // charge V limit x10, charge A x10, discharge A x10, discharge V x10
    put16(&f.data[0], PACK_SERIES * 2 * CELL_MAX_MV / 100);   // stage 2 is 68S
    put16(&f.data[2], ok && !g_safety.regen_inhibit ? 300 : 0);
    put16(&f.data[4], ok && !g_safety.assist_inhibit ? 600 : 0);
    put16(&f.data[6], PACK_SERIES * 2 * CELL_MIN_MV / 100);
    can_send(BUS_EV, &f);

    f.id = 0x355;   // SOC %, SOH %
    put16(&f.data[0], (int)p->soc_pct);
    put16(&f.data[2], 100);
    put16(&f.data[4], (int)(p->soc_pct * 100));
    put16(&f.data[6], 0);
    can_send(BUS_EV, &f);

    f.id = 0x356;   // pack V x100, current A x10, temp C x10
    put16(&f.data[0], (int)(p->pack_mv / 10));
    put16(&f.data[2], (int)(p->current_ma / 100));
    put16(&f.data[4], p->temp_max_c * 10);
    put16(&f.data[6], 0);
    can_send(BUS_EV, &f);
}
