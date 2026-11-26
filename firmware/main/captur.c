// The frame layouts below are PLACEHOLDERS until the Captur BMS frames are decoded from SavvyCAN logs. The
// simulation build uses the same layouts, so the decode path and timeouts are exercised end to end.
#include "captur.h"

#include "config.h"

pack_state_t g_pack;
static int s_series = PACK_SERIES;

#if CONFIG_ZE2_SIM
#define ID_CELLS 0x5D7
#define ID_PACK  0x5D8
#define ID_TEMPS 0x5D9
#define ID_CMD   0x5DA
#else
#define ID_CELLS CAPTUR_ID_CELLS
#define ID_PACK  CAPTUR_ID_PACK
#define ID_TEMPS CAPTUR_ID_TEMPS
#define ID_CMD   CAPTUR_ID_CONTACTOR_CMD
#endif

static inline uint16_t u16(const uint8_t *p) { return p[0] | p[1] << 8; }

bool captur_wants(const can_frame_t *f)
{
    return f->bus == BUS_EV && ID_CELLS && !f->ext && (f->id == ID_CELLS || f->id == ID_PACK || f->id == ID_TEMPS);
}

void captur_decode(const can_frame_t *f, uint32_t rx_ms)
{
    pack_group_t g;
    static const uint8_t MIN_DLC[GRP_COUNT] = {4, 5, 2};
    if (f->ext || f->rtr || f->bus != BUS_EV) return;
    g = f->id == ID_CELLS ? GRP_CELLS : f->id == ID_PACK ? GRP_PACK : f->id == ID_TEMPS ? GRP_TEMPS : GRP_COUNT;
    if (g == GRP_COUNT || f->dlc < MIN_DLC[g]) return;
    if (g == GRP_CELLS) {               // [0..1] min mV, [2..3] max mV
        uint16_t lo = u16(&f->data[0]), hi = u16(&f->data[2]);
        if (lo < 2000 || hi > 4500 || lo > hi) return;   // implausible: ignore, let the group go stale
        g_pack.cell_min_mv = lo;
        g_pack.cell_max_mv = hi;
    } else if (g == GRP_PACK) {         // [0..1] pack V x10, [2..3] current A x10 signed, [4] SOC x2
        uint32_t mv = u16(&f->data[0]) * 100u;
        if (mv < 50000 || mv > 320000 || f->data[4] > 200) return;
        g_pack.pack_mv = mv;
        g_pack.current_ma = (int16_t)u16(&f->data[2]) * 100;
        g_pack.soc_pct = f->data[4] * 0.5f;
    } else {                            // [0] min C +40, [1] max C +40
        int lo = f->data[0] - 40, hi = f->data[1] - 40;
        if (lo < -40 || hi > 100 || lo > hi) return;
        g_pack.temp_min_c = (int8_t)lo;
        g_pack.temp_max_c = (int8_t)hi;
    }
    g_pack.last_ms[g] = rx_ms;
    g_pack.seen[g] = true;
    g_pack.valid = g_pack.seen[GRP_CELLS] && g_pack.seen[GRP_PACK] && g_pack.seen[GRP_TEMPS];
}

bool captur_fresh(uint32_t now_ms)
{
    if (!g_pack.valid) return false;
    for (int g = 0; g < GRP_COUNT; g++) {
        if ((int32_t)(now_ms - g_pack.last_ms[g]) >= BMS_TIMEOUT_MS) return false;
    }
    return true;
}

void captur_set_series(int cells) { s_series = cells; }

bool captur_consistent(void)
{
    // the BMS reports pack voltage and cell min/max separately: a wrong scale, a stuck field or a frame from
    // the wrong source shows up as a pack voltage outside series x [min, max], allowing for timing and IR drop
    uint32_t lo = (uint32_t)s_series * g_pack.cell_min_mv, hi = (uint32_t)s_series * g_pack.cell_max_mv;
    uint32_t tol = g_pack.pack_mv * PACK_TOL_PCT / 100 + PACK_TOL_MV;
    return g_pack.pack_mv + tol >= lo && g_pack.pack_mv <= hi + tol;
}

void captur_tick(uint32_t now_ms, bool contactors_wanted)
{
    static uint32_t last;
    if (!ID_CMD || now_ms - last < 100) return;
    last = now_ms;
    // PLACEHOLDER: the Captur HEV ECU's contactor/keep-alive request, 10 Hz
    can_frame_t f = {.id = ID_CMD, .dlc = 8};
    f.data[0] = contactors_wanted ? 1 : 0;
    can_send(BUS_EV, &f);
}
