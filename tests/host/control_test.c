// Host tests of the stage-1 safety chain: the firmware's own captur.c, safety.c, contactors.c, ignition.c,
// control.c and zombie.c, compiled for the PC against a small model of the board and pack:
//   - the Captur BMS answering UDS reads (DIDs and scales as on the bench);
//   - Captur contactors (main+, precharge in parallel with it, negative hard-wired) with optional welds;
//   - the U10/U11 enable latch: WDI rising edge clocks MCU_EN, 1.36 s without an edge clears it;
//   - the AMC3311 sense (valid or not) and the board supply.
// One scenario per process (the firmware keeps static state): ./control_test <scenario>; exit 0 = pass.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "captur.h"
#include "config.h"
#include "contactors.h"
#include "control.h"
#include "hal.h"
#include "safety.h"
#include "zombie.h"

// ------------------------------------------------------------------ board and pack model
static bool out[OUT_COUNT];
static bool weld_pos, weld_pre, sense_ok = true, latch_q;
static int32_t pack_mv = 125630, link_mv, link_forced = -1, vbat_mv = 13800;   // 34S2P: 34 x 3.695 V
static uint32_t now = 1000, last_edge;
static can_frame_t last351, keepalive[4];
static int n_keepalive;

void hal_out(hal_out_t o, bool on)
{
    if (o == OUT_WDI && on && !out[OUT_WDI]) {   // rising edge: U10 clocks MCU_EN in
        latch_q = out[OUT_MCU_EN];
        last_edge = now;
    }
    out[o] = on;
}

bool hal_bus_mv(int32_t *mv)
{
    *mv = link_forced >= 0 ? link_forced : link_mv;
    return sense_ok;
}

bool hal_vbat_mv(int32_t *mv)
{
    *mv = vbat_mv;
    return true;
}

// ------------------------------------------------------------------ Captur BMS (UDS 22 replies)
static uint16_t cell_min = 3680, cell_max = 3710;
static int32_t cell_sum_mv = -1;   // -1: 68 x the mean of min and max
static int temp_min = 18, temp_max = 22;
static bool send_cells = true, send_pack = true, send_temps = true;
static can_frame_t pending[8];
static int n_pending;

static void bms_reply(const can_frame_t *q)
{
    uint16_t did = q->data[2] << 8 | q->data[3];
    uint32_t v;
    int len = 2;
    bool cells = did == 0x9007 || did == 0x9009 || did == 0x9006, temps = did == 0x9013 || did == 0x9014;
    if ((cells && !send_cells) || (temps && !send_temps) || (!cells && !temps && !send_pack)) return;
    uint32_t sum = cell_sum_mv >= 0 ? (uint32_t)cell_sum_mv : 68u * (cell_min + cell_max) / 2;
    switch (did) {
    case 0x9007: v = cell_max * 1024u / 1000; break;
    case 0x9009: v = cell_min * 1024u / 1000; break;
    case 0x9006: v = (uint32_t)((uint64_t)sum * 1024 / 1000); len = 4; break;
    case 0x9013: v = (temp_min + 40) * 16; break;
    case 0x9014: v = (temp_max + 40) * 16; break;
    case 0x9001: v = 6200 + 300; break;
    case 0x9005: v = 2513; break;
    default: return;
    }
    can_frame_t r = {.id = CAPTUR_UDS_RESP, .ext = 1, .dlc = 8, .bus = BUS_EV,
                     .data = {(uint8_t)(3 + len), 0x62, q->data[2], q->data[3], 0xAA, 0xAA, 0xAA, 0xAA}};
    for (int i = 0; i < len; i++) r.data[4 + i] = (uint8_t)(v >> (8 * (len - 1 - i)));
    if (n_pending < 8) pending[n_pending++] = r;
}

bool can_send(bus_id_t bus, const can_frame_t *f)
{
    if (f->id == 0x351) last351 = *f;
    if (f->id == CAPTUR_KEEPALIVE_ID && n_keepalive < 4) keepalive[n_keepalive++] = *f;
    if (f->ext && f->id == CAPTUR_UDS_REQ && f->data[0] == 3 && f->data[1] == 0x22) bms_reply(f);
    return true;
}

static bool coil(hal_out_t o) { return out[o] && latch_q; }   // a coil needs its high side and the master FET

static void model_step(void)
{
    if (now - last_edge >= 1360) latch_q = false;   // TPS3431 minimum timeout clears U10
    bool pos = coil(OUT_HS_MAINP) || weld_pos, pre = coil(OUT_HS_PRE) || weld_pre;   // negative hard-wired
    if (pos) link_mv = pack_mv;
    else if (pre) link_mv += (pack_mv - link_mv) / 15;   // tau ~150 ms at 10 ms steps
    else link_mv -= link_mv / 500;                            // bleed, tau ~5 s
}

// one 10 ms control pass, in main.c's order
static bool stage1 = true;
static void step(void)
{
    now += CONTROL_PERIOD_MS;
    contactors_kick_watchdog(now);
    int n = n_pending;                       // replies to last pass's requests arrive now
    n_pending = 0;
    for (int i = 0; i < n; i++) captur_decode(&pending[i], now);
    control_safety_step(now, stage1);
    zombie_tick(now, !stage1);
    captur_tick(now);
    model_step();
}

static void run(uint32_t ms) { for (uint32_t t = 0; t < ms; t += CONTROL_PERIOD_MS) step(); }

static int fails;
#define CHECK(c, msg) do { if (!(c)) { fprintf(stderr, "FAIL %s:%d %s\n", __func__, __LINE__, msg); fails++; } } while (0)
static bool any_coil(void) { return coil(OUT_HS_MAINN) || coil(OUT_HS_MAINP) || coil(OUT_HS_PRE); }

// ------------------------------------------------------------------ scenarios
static void normal_close(void)
{
    bool saw_overlap = false, pos_before_overlap = false;
    for (int i = 0; i < 300 && contactors_state() != CT_CLOSED; i++) {
        step();
        if (coil(OUT_HS_MAINP) && !coil(OUT_HS_PRE) && !saw_overlap) pos_before_overlap = true;
        if (coil(OUT_HS_MAINP) && coil(OUT_HS_PRE)) saw_overlap = true;
    }
    CHECK(contactors_state() == CT_CLOSED, "closes on a healthy pack");
    CHECK(saw_overlap && !pos_before_overlap, "precharge held while main+ picks up");
    CHECK(coil(OUT_HS_MAINP) && !coil(OUT_HS_PRE) && !out[OUT_HS_MAINN], "closed: main+ on, precharge off, spare off");
    CHECK(g_pack.pack_mv > 124000 && g_pack.pack_mv < 127000, "34S2P reference is half the 68-cell sum");
    CHECK(g_safety.taps_enabled, "taps on");
}

static void only_cells(void)
{
    send_pack = send_temps = false;
    run(2000);
    CHECK(!g_safety.contactors_permitted && !any_coil(), "cells alone never permit a close");
}

static void stale_groups_stage2(void)
{
    stage1 = false;
    run(1000);
    CHECK(last351.data[2] || last351.data[3], "stage 2 advertises charge current when healthy");
    send_cells = send_temps = false;
    run(1000);
    CHECK(!g_safety.contactors_permitted, "stale cells/temps revoke permission");
    CHECK(!last351.data[2] && !last351.data[3] && !last351.data[4] && !last351.data[5], "stage 2 limits drop to 0 A");
    CHECK(!any_coil() && !out[OUT_HS_MAINN] && !out[OUT_HS_PRE], "stage 2 never drives the contactors");
}

static void live_link_while_open(void)
{
    link_forced = 25000;
    run(1000);
    CHECK(contactors_faulted(), "25 V on an open link is a fault");
    CHECK(!g_safety.contactors_permitted && !g_safety.taps_enabled, "local fault revokes permission and taps");
    CHECK(!any_coil(), "nothing energised");
    link_forced = -1;
    run(3000);
    CHECK(contactors_faulted() && !any_coil(), "fault stays latched with ignition on");
}

static void soft_trip_before_start(void)
{
    cell_max = 4185;
    run(2000);
    CHECK(g_safety.level == SAFE_SOFT_TRIP, "4.185 V is a soft trip");
    CHECK(!out[OUT_HS_MAINN] && !out[OUT_HS_PRE] && !out[OUT_HS_MAINP], "soft trip never starts a close");
}

static void soft_trip_while_closed(void)
{
    normal_close();
    cell_max = 4185;
    run(500);
    CHECK(contactors_state() == CT_CLOSED, "soft trip keeps a closed pack closed (taps float instead)");
    CHECK(!g_safety.taps_enabled, "taps off");
}

static void pack_disagrees_with_cells(void)
{
    cell_sum_mv = 110000;   // the extreme cells say 68 x 3.68-3.71 V = 250-252 V
    run(3000);
    CHECK(!coil(OUT_HS_MAINP) && !out[OUT_HS_MAINP], "main+ never commanded");
    CHECK(!g_safety.contactors_permitted, "inconsistent pack voltage is a hard trip");
}

static void welded_pos(void)
{
    weld_pos = true;
    run(2000);
    CHECK(contactors_faulted() && strstr(contactors_fault(), "welded"), "welded main+: link live with coils off");
    CHECK(!out[OUT_HS_PRE] && !out[OUT_HS_MAINP], "nothing commanded");
}

static void welded_pre(void)
{
    weld_pre = true;
    run(2000);
    CHECK(contactors_faulted() && strstr(contactors_fault(), "welded"), "welded precharge: link live with coils off");
}

static void keepalive_frames(void)
{
    run(200);
    CHECK(n_keepalive == 4, "keep-alive sent");
    for (int i = 0; i < 4; i++) {   // counters 0-3 with byte 8 D0: CRCs from the bench log
        CHECK(keepalive[i].id == 0x0F5 && !keepalive[i].ext && keepalive[i].data[1] == i, "0x0F5, counter");
    }
    CHECK(keepalive[0].data[2] == 0x1B && keepalive[1].data[2] == 0x5D, "CRC-8 matches the logged frames");
    uint8_t c8[7] = {0x7D, 2, 0xFF, 0xD7, 0xF8, 0x00, 0xC8}, e0[7] = {0x7D, 3, 0xFF, 0xD7, 0xF8, 0x00, 0xE0};
    CHECK(captur_crc8(c8, 7) == 0xB2 && captur_crc8(e0, 7) == 0x9B, "CRC-8 with other byte-8 values");
}

static void sense_invalid(void)
{
    sense_ok = false;
    bool ever = false;
    for (int i = 0; i < 200; i++) { step(); ever |= out[OUT_HS_PRE] || out[OUT_HS_MAINN] || out[OUT_HS_MAINP]; }
    CHECK(contactors_faulted() && !ever, "no coil energised without a valid dead-link reading");
}

static void sense_lost_while_closed(void)
{
    normal_close();
    sense_ok = false;
    step();
    CHECK(contactors_faulted() && !any_coil(), "losing the sense while closed opens everything");
}

static void stall_and_resume(void)
{
    normal_close();
    now += 2000;              // control loop frozen 2 s: no WDI edges
    model_step();
    CHECK(!latch_q && !any_coil(), "watchdog clears the latch during the stall");
    run(500);                 // loop resumes with MCU_EN still high in the firmware's view
    CHECK(!any_coil(), "resume does not re-energise any coil");
    CHECK(contactors_faulted(), "stall is a latched fault");
    run(3000);
    CHECK(!any_coil(), "still open: re-arm needs key-off");
}

static void crank_dip_keeps_trip(void)
{
    link_forced = 25000;
    run(500);
    CHECK(contactors_faulted(), "fault set");
    link_forced = -1;
    vbat_mv = 5000;           // crank dip, 0.8 s
    run(800);
    vbat_mv = 13800;
    run(1000);
    CHECK(contactors_faulted() && !g_safety.contactors_permitted, "a crank dip does not clear the fault");
    vbat_mv = 0;              // key-off
    run(2500);
    vbat_mv = 13800;
    run(2000);
    CHECK(!contactors_faulted(), "a real key-off clears it");
}

static void decoder_checks(void)
{
    send_cells = send_pack = send_temps = false;
    can_frame_t f = {.bus = BUS_EV, .id = CAPTUR_UDS_RESP, .ext = 1, .dlc = 8, .data = {0x05, 0x62, 0x90, 0x13, 0x03, 0xA0}};
    can_frame_t g = f;
    g.data[3] = 0x14;
    g.dlc = 5;
    captur_decode(&f, now); captur_decode(&g, now);
    CHECK(!g_pack.seen[GRP_TEMPS], "short DLC rejected");
    g.dlc = 8; g.rtr = 1;
    captur_decode(&g, now);
    CHECK(!g_pack.seen[GRP_TEMPS], "RTR rejected");
    g.rtr = 0; g.ext = 0;
    captur_decode(&g, now);
    CHECK(!g_pack.seen[GRP_TEMPS], "standard ID rejected");
    g.ext = 1; g.data[0] = 0x06;
    captur_decode(&g, now);
    CHECK(!g_pack.seen[GRP_TEMPS], "wrong ISO-TP length rejected");
    g.data[0] = 0x05; g.data[1] = 0x7F;
    captur_decode(&g, now);
    CHECK(!g_pack.seen[GRP_TEMPS], "negative response ignored");
    g.data[1] = 0x62;
    captur_decode(&f, now - 600); captur_decode(&g, now - 400);   // arrived 600 / 400 ms ago, decoded now
    CHECK(g_pack.seen[GRP_TEMPS] && g_pack.last_ms[GRP_TEMPS] == now - 600, "freshness from the oldest arrival");
    CHECK(g_pack.temp_min_c == 18 && g_pack.temp_max_c == 18, "(raw - 640) / 16");
}

static const struct { const char *name; void (*fn)(void); } SCEN[] = {
    {"normal_close", normal_close}, {"only_cells", only_cells}, {"stale_groups_stage2", stale_groups_stage2},
    {"live_link_while_open", live_link_while_open}, {"soft_trip_before_start", soft_trip_before_start},
    {"soft_trip_while_closed", soft_trip_while_closed}, {"pack_disagrees_with_cells", pack_disagrees_with_cells},
    {"welded_pos", welded_pos}, {"welded_pre", welded_pre}, {"sense_invalid", sense_invalid},
    {"sense_lost_while_closed", sense_lost_while_closed}, {"stall_and_resume", stall_and_resume},
    {"crank_dip_keeps_trip", crank_dip_keeps_trip}, {"decoder_checks", decoder_checks},
    {"keepalive_frames", keepalive_frames},
};

int main(int argc, char **argv)
{
    if (argc < 2) {
        for (size_t i = 0; i < sizeof SCEN / sizeof SCEN[0]; i++) printf("%s\n", SCEN[i].name);
        return 0;
    }
    captur_set_series(PACK_SERIES);
    contactors_init();
    for (size_t i = 0; i < sizeof SCEN / sizeof SCEN[0]; i++) {
        if (strcmp(argv[1], SCEN[i].name)) continue;
        SCEN[i].fn();
        return fails ? 1 : 0;
    }
    fprintf(stderr, "unknown scenario %s\n", argv[1]);
    return 2;
}
