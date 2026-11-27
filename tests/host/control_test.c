// Host tests of the stage-1 safety chain: the firmware's own captur.c, safety.c, contactors.c, ignition.c,
// control.c and zombie.c, compiled for the PC against a small model of the board and pack:
//   - the Captur BMS answering UDS reads (DIDs and scales as on the bench);
//   - Captur contactors (main+, precharge in parallel with it, negative hard-wired) with optional welds;
//   - the U10/U11 enable latch: a WDI rising edge clocks MCU_EN into U10; U11 counts falling edges, and 1.36 s
//     without one clears U10;
//   - the AMC3311 sense (valid or not) and the board supply (and whether its ADC read works);
//   - U8 MultiSense precharge-coil current: open or shorted coil, or a high side stuck on, on request.
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
static bool weld_pos, weld_pre, main_open, pre_coil_open, pre_coil_short, pre_stuck_on, sense_ok = true, vbat_ok = true, latch_q;
static int pre_div = 15;   // precharge: link closes 1/pre_div of the gap per 10 ms
static int32_t pack_mv = 125630, link_mv, link_forced = -1, vbat_mv = 13800;   // 34S2P: 34 x 3.695 V
static uint32_t now = 1000, last_kick;
static can_frame_t last351, keepalive[4];
static int n_keepalive;

void hal_out(hal_out_t o, bool on)
{
    if (o == OUT_WDI && on && !out[OUT_WDI]) latch_q = out[OUT_MCU_EN];   // rising edge: U10 clocks MCU_EN in
    if (o == OUT_WDI && !on && out[OUT_WDI]) last_kick = now;              // falling edge: U11 kicked
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
    return vbat_ok;
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

bool hal_precharge_coil_ma(int32_t *ma)
{
    bool on = (out[OUT_HS_PRE] || pre_stuck_on) && latch_q && !pre_coil_open;
    *ma = !on ? 0 : pre_coil_short ? 4000 : 214;   // shorted: the VND7050 limits and drives VSENSEH
    return true;
}

static void model_step(void)
{
    if (now - last_kick >= 1360) latch_q = false;   // TPS3431 minimum timeout clears U10
    bool pos = (coil(OUT_HS_MAINP) && !main_open) || weld_pos, pre = ((coil(OUT_HS_PRE) || (pre_stuck_on && latch_q)) && !pre_coil_open) || weld_pre;   // neg. wired
    if (pos) link_mv = pack_mv;
    else if (pre) link_mv += (pack_mv - link_mv) / pre_div;   // tau ~150 ms at 10 ms steps by default
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
    bool saw_overlap = false, pos_before_overlap = false, taps_early = false;
    for (int i = 0; i < 300 && contactors_state() != CT_CLOSED; i++) {
        step();
        if (coil(OUT_HS_MAINP) && !coil(OUT_HS_PRE) && !saw_overlap) pos_before_overlap = true;
        if (coil(OUT_HS_MAINP) && coil(OUT_HS_PRE)) saw_overlap = true;
        taps_early |= g_safety.taps_enabled;
    }
    CHECK(contactors_state() == CT_CLOSED, "closes on a healthy pack");
    CHECK(!taps_early, "taps stay off until closure is verified");
    step();
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

// main+ coil energised but the contact never makes: the link, charged through precharge, reads ~100 %
static void main_stuck_open(void)
{
    main_open = true;
    bool taps = false, closed = false;
    for (int i = 0; i < 300; i++) { step(); taps |= g_safety.taps_enabled; closed |= contactors_state() == CT_CLOSED; }
    CHECK(!closed && !taps, "never CLOSED, taps never on");
    CHECK(contactors_faulted() && strstr(contactors_fault(), "main+"), "main+ fault (low or decaying link)");
    CHECK(!any_coil(), "everything open");
}

// same, with the link fully charged when precharge drops (worst case for a voltage-only check)
static void main_stuck_open_full_link(void)
{
    main_open = true;
    pre_div = 4;              // precharge reaches ~100 % during the 100 ms overlap
    for (int i = 0; i < 300; i++) step();
    CHECK(contactors_faulted() && strstr(contactors_fault(), "main+ open"), "caught by droop, not by level");
}

static void soft_trip_during_precharge(void)
{
    for (int i = 0; i < 100 && contactors_state() != CT_PRECHARGE; i++) step();
    CHECK(contactors_state() == CT_PRECHARGE, "precharging");
    cell_max = 4185;          // soft limit crossed mid-close
    bool main_cmd = false;
    for (int i = 0; i < 200; i++) { step(); main_cmd |= out[OUT_HS_MAINP]; }
    CHECK(!main_cmd && contactors_faulted() && !any_coil(), "close aborted, main+ never commanded");
}

static void link_reads_high(void)
{
    for (int i = 0; i < 100 && contactors_state() != CT_PRECHARGE; i++) step();
    link_forced = 170000;     // bus sense jumps to 170 V with the BMS still saying 125.6 V
    bool main_cmd = false;
    for (int i = 0; i < 100; i++) { step(); main_cmd |= out[OUT_HS_MAINP]; }
    CHECK(!main_cmd && contactors_faulted() && strstr(contactors_fault(), "above pack"), "implausible link: fault");
}

static void late_precharge(void)
{
    pre_div = 140;            // tau 1.4 s: 90 % only after ~3.2 s
    bool main_cmd = false;
    for (int i = 0; i < 500; i++) { step(); main_cmd |= out[OUT_HS_MAINP]; }
    CHECK(!main_cmd && contactors_faulted() && strstr(contactors_fault(), "timeout"), "deadline wins over a late rise");
}

static void ignition_sense_lost(void)
{
    normal_close();
    vbat_ok = false;          // ADC stops returning valid data, CPU still running
    run(IGN_INVALID_MS + 30);
    CHECK(!any_coil() && contactors_state() != CT_CLOSED, "coils off within IGN_INVALID_MS");
    vbat_ok = true;
    run(2000);
    CHECK(!any_coil() && !g_safety.contactors_permitted, "latched after the sense recovers");
}

static void reset_latch(void)
{
    safety_boot_latch("reset while running: brownout");
    run(2000);
    CHECK(!any_coil() && !out[OUT_HS_PRE], "no close after an unexpected reset with the key on");
    vbat_mv = 0;              // real key-off
    run(2500);
    vbat_mv = 13800;
    for (int i = 0; i < 400 && contactors_state() != CT_CLOSED; i++) step();
    CHECK(contactors_state() == CT_CLOSED, "closes after a real key-off");
}

static void taps_need_island(void)
{
    normal_close();
    safety_island_report(false);
    step();
    CHECK(contactors_state() == CT_CLOSED && !g_safety.taps_enabled, "island lost: taps float, pack stays closed");
    safety_island_report(true);
    step();
    CHECK(g_safety.taps_enabled, "island back: taps on");
}

static void clock_wrap(void)
{
    now = 0xFFFFFFFFu - 300;  // 32-bit millisecond counter wraps mid-close
    last_kick = now;
    normal_close();
}

static void precharge_coil_open(void)
{
    pre_coil_open = true;     // coil, its harness or its connector open: no current, link never charges
    bool main_cmd = false;
    uint32_t t0 = now;
    for (int i = 0; i < 100 && !contactors_faulted(); i++) { step(); main_cmd |= out[OUT_HS_MAINP]; }
    CHECK(contactors_faulted() && strstr(contactors_fault(), "precharge coil current low"), "named as a coil fault");
    CHECK(now - t0 < 300 && !main_cmd && !any_coil(), "well before the precharge deadline, main+ never commanded");
}

static void precharge_coil_shorted(void)
{
    pre_coil_short = true;
    for (int i = 0; i < 100 && !contactors_faulted(); i++) step();
    CHECK(contactors_faulted() && strstr(contactors_fault(), "precharge coil current high"), "shorted coil: fault");
    CHECK(!any_coil() && !out[OUT_HS_MAINP], "everything open, main+ never commanded");
}

static void precharge_stuck_on(void)
{
    normal_close();
    run(100);
    CHECK(contactors_state() == CT_CLOSED && contactors_coil_ma() == 0, "closed: precharge reads off");
    pre_stuck_on = true;      // precharge high side fails short while closed
    run(100);
    CHECK(contactors_faulted() && strstr(contactors_fault(), "commanded off"), "stuck-on driver: fault");
    CHECK(!out[OUT_HS_MAINP] && !latch_q, "main+ dropped and the master FET opened, so the stuck coil is off");
}

static const struct { const char *name; void (*fn)(void); } SCEN[] = {
    {"normal_close", normal_close}, {"only_cells", only_cells}, {"stale_groups_stage2", stale_groups_stage2},
    {"live_link_while_open", live_link_while_open}, {"soft_trip_before_start", soft_trip_before_start},
    {"soft_trip_while_closed", soft_trip_while_closed}, {"pack_disagrees_with_cells", pack_disagrees_with_cells},
    {"welded_pos", welded_pos}, {"welded_pre", welded_pre}, {"sense_invalid", sense_invalid},
    {"sense_lost_while_closed", sense_lost_while_closed}, {"stall_and_resume", stall_and_resume},
    {"crank_dip_keeps_trip", crank_dip_keeps_trip}, {"decoder_checks", decoder_checks},
    {"keepalive_frames", keepalive_frames}, {"main_stuck_open", main_stuck_open},
    {"main_stuck_open_full_link", main_stuck_open_full_link},
    {"soft_trip_during_precharge", soft_trip_during_precharge}, {"link_reads_high", link_reads_high},
    {"late_precharge", late_precharge}, {"ignition_sense_lost", ignition_sense_lost}, {"reset_latch", reset_latch},
    {"taps_need_island", taps_need_island}, {"clock_wrap", clock_wrap},
    {"precharge_coil_open", precharge_coil_open}, {"precharge_coil_shorted", precharge_coil_shorted},
    {"precharge_stuck_on", precharge_stuck_on},
};

int main(int argc, char **argv)
{
    if (argc < 2) {
        for (size_t i = 0; i < sizeof SCEN / sizeof SCEN[0]; i++) printf("%s\n", SCEN[i].name);
        return 0;
    }
    captur_set_series(PACK_SERIES);
    contactors_init();
    safety_island_report(true);   // the island model isn't part of this binary: healthy unless a test says not
    for (size_t i = 0; i < sizeof SCEN / sizeof SCEN[0]; i++) {
        if (strcmp(argv[1], SCEN[i].name)) continue;
        SCEN[i].fn();
        return fails ? 1 : 0;
    }
    fprintf(stderr, "unknown scenario %s\n", argv[1]);
    return 2;
}
