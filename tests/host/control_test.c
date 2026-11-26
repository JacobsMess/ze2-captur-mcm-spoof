// Host tests of the stage-1 safety chain: the firmware's own captur.c, safety.c, contactors.c, ignition.c,
// control.c and zombie.c, compiled for the PC against a small model of the board and pack:
//   - Captur contactors (precharge in parallel with main+) with optional welded poles and a link-voltage model;
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
static bool weld_neg, weld_pos, sense_ok = true, latch_q;
static int32_t pack_mv = 125000, link_mv, link_forced = -1, vbat_mv = 13800;
static uint32_t now = 1000, last_edge;
static can_frame_t last351;

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

bool can_send(bus_id_t bus, const can_frame_t *f)
{
    if (f->id == 0x351) last351 = *f;
    return true;
}

static bool coil(hal_out_t o) { return out[o] && latch_q; }   // a coil needs its high side and the master FET

static void model_step(void)
{
    if (now - last_edge >= 1360) latch_q = false;   // TPS3431 minimum timeout clears U10
    bool neg = coil(OUT_HS_MAINN) || weld_neg, pos = coil(OUT_HS_MAINP) || weld_pos;
    bool pre = coil(OUT_HS_PRE);
    if (neg && pos) link_mv = pack_mv;
    else if (neg && pre) link_mv += (pack_mv - link_mv) / 15;   // tau ~150 ms at 10 ms steps
    else link_mv -= link_mv / 500;                            // bleed, tau ~5 s
}

// ------------------------------------------------------------------ BMS frames (simulation-build layouts)
static uint16_t cell_min = 3680, cell_max = 3710;
static int temp_min = 18, temp_max = 22;
static bool send_cells = true, send_pack = true, send_temps = true;
static uint32_t pack_frame_mv = 125000;

static void put16(uint8_t *p, unsigned v) { p[0] = v; p[1] = v >> 8; }

static void bms_frames(void)
{
    if (now % 100) return;
    can_frame_t f = {.bus = BUS_EV, .dlc = 8};
    if (send_cells) { f.id = 0x5D7; put16(&f.data[0], cell_min); put16(&f.data[2], cell_max); captur_decode(&f, now); }
    if (send_pack) {
        memset(f.data, 0, 8); f.id = 0x5D8; put16(&f.data[0], pack_frame_mv / 100); f.data[4] = 120;
        captur_decode(&f, now);
    }
    if (send_temps) { memset(f.data, 0, 8); f.id = 0x5D9; f.data[0] = temp_min + 40; f.data[1] = temp_max + 40; captur_decode(&f, now); }
}

// one 10 ms control pass, in main.c's order
static bool stage1 = true;
static void step(void)
{
    now += CONTROL_PERIOD_MS;
    contactors_kick_watchdog(now);
    bms_frames();
    control_safety_step(now, stage1);
    zombie_tick(now, !stage1);
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
    CHECK(coil(OUT_HS_MAINN) && coil(OUT_HS_MAINP) && !coil(OUT_HS_PRE), "closed: mains on, precharge off");
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
    pack_frame_mv = 50000;   // cells say 34 x 3.68 V = 125 V
    pack_mv = 50000;
    run(3000);
    CHECK(!coil(OUT_HS_MAINP) && !out[OUT_HS_MAINP], "main+ never commanded");
    CHECK(!g_safety.contactors_permitted, "inconsistent pack voltage is a hard trip");
}

static void welded_neg(void)
{
    weld_neg = true;
    run(2000);
    CHECK(contactors_faulted() && strstr(contactors_fault(), "main-"), "welded main- found with precharge alone");
    CHECK(!out[OUT_HS_MAINP], "main+ never commanded");
}

static void welded_pos(void)
{
    weld_pos = true;
    run(2000);
    CHECK(contactors_faulted() && strstr(contactors_fault(), "main+"), "welded main+ found with main- alone");
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
    can_frame_t f = {.bus = BUS_EV, .id = 0x5D7, .dlc = 3};
    put16(&f.data[0], 3600); put16(&f.data[2], 3700);
    captur_decode(&f, now);
    CHECK(!g_pack.seen[GRP_CELLS], "short DLC rejected");
    f.dlc = 4; f.rtr = 1;
    captur_decode(&f, now);
    CHECK(!g_pack.seen[GRP_CELLS], "RTR rejected");
    f.rtr = 0; f.ext = 1;
    captur_decode(&f, now);
    CHECK(!g_pack.seen[GRP_CELLS], "extended ID rejected");
    f.ext = 0;
    captur_decode(&f, now - 600);   // arrived 600 ms ago, decoded now
    CHECK(g_pack.seen[GRP_CELLS] && g_pack.last_ms[GRP_CELLS] == now - 600, "freshness from arrival time");
}

static const struct { const char *name; void (*fn)(void); } SCEN[] = {
    {"normal_close", normal_close}, {"only_cells", only_cells}, {"stale_groups_stage2", stale_groups_stage2},
    {"live_link_while_open", live_link_while_open}, {"soft_trip_before_start", soft_trip_before_start},
    {"soft_trip_while_closed", soft_trip_while_closed}, {"pack_disagrees_with_cells", pack_disagrees_with_cells},
    {"welded_neg", welded_neg}, {"welded_pos", welded_pos}, {"sense_invalid", sense_invalid},
    {"sense_lost_while_closed", sense_lost_while_closed}, {"stall_and_resume", stall_and_resume},
    {"crank_dip_keeps_trip", crank_dip_keeps_trip}, {"decoder_checks", decoder_checks},
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
