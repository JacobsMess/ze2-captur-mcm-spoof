#include "captur.h"

#include "config.h"

pack_state_t g_pack;
static int s_series = PACK_SERIES;

typedef struct {
    uint16_t did;
    uint8_t len;           // data bytes after 62 hi lo
    pack_group_t grp;
    uint32_t raw;
    uint32_t last_ms;
    bool seen;
} did_t;

// polled round-robin, one per 20 ms: every value is under 150 ms old in normal running
static did_t DIDS[] = {
    {.did = 0x9007, .len = 2, .grp = GRP_CELLS}, {.did = 0x9009, .len = 2, .grp = GRP_CELLS},
    {.did = 0x9006, .len = 4, .grp = GRP_CELLS},
    {.did = 0x9013, .len = 2, .grp = GRP_TEMPS}, {.did = 0x9014, .len = 2, .grp = GRP_TEMPS},
    {.did = 0x9001, .len = 2, .grp = GRP_PACK}, {.did = 0x9005, .len = 2, .grp = GRP_PACK},
};
#define N_DIDS (sizeof DIDS / sizeof DIDS[0])

uint8_t captur_crc8(const uint8_t *p, int n)
{
    uint8_t crc = 0xC4;
    for (int i = 0; i < n; i++) {
        crc ^= p[i];
        for (int b = 0; b < 8; b++) crc = crc & 0x80 ? (uint8_t)(crc << 1 ^ 0x1D) : (uint8_t)(crc << 1);
    }
    return crc;
}

bool captur_wants(const can_frame_t *f)
{
    return f->bus == BUS_EV && f->ext && f->id == CAPTUR_UDS_RESP;
}

static did_t *find(uint16_t did)
{
    for (unsigned i = 0; i < N_DIDS; i++) if (DIDS[i].did == did) return &DIDS[i];
    return 0;
}

static uint32_t mv_1024(uint32_t raw) { return (uint32_t)((uint64_t)raw * 1000 / 1024); }

// a group's values are taken only once all its DIDs have fresh, plausible replies
static void update_group(pack_group_t g)
{
    uint32_t oldest = 0;
    bool first = true;
    for (unsigned i = 0; i < N_DIDS; i++) {
        if (DIDS[i].grp != g) continue;
        if (!DIDS[i].seen) return;
        if (first || (int32_t)(DIDS[i].last_ms - oldest) < 0) oldest = DIDS[i].last_ms;
        first = false;
    }
    if (g == GRP_CELLS) {
        uint32_t hi = mv_1024(find(0x9007)->raw), lo = mv_1024(find(0x9009)->raw), sum = mv_1024(find(0x9006)->raw);
        if (lo < 2000 || hi > 4500 || lo > hi) return;   // implausible: ignore, let the group go stale
        g_pack.cell_min_mv = lo;
        g_pack.cell_max_mv = hi;
        g_pack.cell_sum_mv = sum;
        g_pack.pack_mv = (uint32_t)((uint64_t)sum * s_series / CAPTUR_CELLS);
    } else if (g == GRP_TEMPS) {
        int lo = ((int)find(0x9013)->raw - 640) / 16, hi = ((int)find(0x9014)->raw - 640) / 16;
        if (lo < -40 || hi > 100 || lo > hi) return;
        g_pack.temp_min_c = (int8_t)lo;
        g_pack.temp_max_c = (int8_t)hi;
    } else {
        int32_t soc = (int32_t)find(0x9001)->raw - 300;
        if (soc < 0 || soc > 10000) return;
        g_pack.soc_pct = soc * 0.01f;
        g_pack.bms_pack_mv = find(0x9005)->raw * 100;
        g_pack.current_ma = 0;
    }
    g_pack.last_ms[g] = oldest;
    g_pack.seen[g] = true;
    g_pack.valid = g_pack.seen[GRP_CELLS] && g_pack.seen[GRP_PACK] && g_pack.seen[GRP_TEMPS];
}

void captur_decode(const can_frame_t *f, uint32_t rx_ms)
{
    // single-frame positive reply: [0] length, [1] 0x62, [2..3] DID, then the value
    if (!captur_wants(f) || f->rtr || f->dlc < 4 || f->data[1] != 0x62) return;
    did_t *d = find((uint16_t)(f->data[2] << 8 | f->data[3]));
    if (!d || f->data[0] != 3 + d->len || f->dlc < 4 + d->len) return;
    uint32_t v = 0;
    for (int i = 0; i < d->len; i++) v = v << 8 | f->data[4 + i];
    d->raw = v;
    d->last_ms = rx_ms;
    d->seen = true;
    update_group(d->grp);
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
    // the BMS reports the cell sum and the extreme cells separately: a wrong scale, a stuck value or a reply
    // from the wrong DID shows up as a sum outside 68 x [min, max], allowing for timing between the reads
    uint32_t lo = CAPTUR_CELLS * (uint32_t)g_pack.cell_min_mv, hi = CAPTUR_CELLS * (uint32_t)g_pack.cell_max_mv;
    uint32_t tol = g_pack.cell_sum_mv * PACK_TOL_PCT / 100 + PACK_TOL_MV;
    return g_pack.cell_sum_mv + tol >= lo && g_pack.cell_sum_mv <= hi + tol;
}

void captur_tick(uint32_t now_ms)
{
    static uint32_t last;
    static uint8_t counter;
    static unsigned next;
    if (now_ms - last < CAPTUR_KEEPALIVE_MS) return;
    last = now_ms;

    can_frame_t k = {.id = CAPTUR_KEEPALIVE_ID, .dlc = 8,
                     .data = {0x7D, (uint8_t)(counter++ & 0x0F), 0, 0xFF, 0xD7, 0xF8, 0x00, 0xD0}};
    uint8_t body[7] = {k.data[0], k.data[1], k.data[3], k.data[4], k.data[5], k.data[6], k.data[7]};
    k.data[2] = captur_crc8(body, 7);
    can_send(BUS_EV, &k);

    can_frame_t r = {.id = CAPTUR_UDS_REQ, .ext = 1, .dlc = 8,
                     .data = {0x03, 0x22, (uint8_t)(DIDS[next].did >> 8), (uint8_t)DIDS[next].did, 0xAA, 0xAA, 0xAA, 0xAA}};
    can_send(BUS_EV, &r);
    next = (next + 1) % N_DIDS;
}
