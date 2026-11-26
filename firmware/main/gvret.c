#include "gvret.h"

#include <string.h>
#include "can_types.h"
#include "canlog.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "net.h"
#include "safety.h"
#include "stats.h"

static const char *TAG = "gvret";
static bool s_binary;

size_t gvret_encode(const void *frame, uint8_t *o)
{
    const can_frame_t *f = frame;
    uint32_t id = f->id | (f->ext ? 0x80000000u : 0);
    o[0] = 0xF1;
    o[1] = 0x00;
    memcpy(&o[2], &f->ts_us, 4);
    memcpy(&o[6], &id, 4);
    o[10] = (f->dlc & 0x0F) | (f->bus << 4);
    memcpy(&o[11], f->data, f->dlc);
    o[11 + f->dlc] = 0;
    return 12 + f->dlc;
}

static void put_bus_params(uint8_t *o, int bus)
{
    uint32_t speed = CAN_BITRATE;
    o[0] = 0x01 | (bus == BUS_DASH ? 0x10 : 0);   // enabled; dash tap is listen-only
    memcpy(&o[1], &speed, 4);
}

static void handle_cmd(const uint8_t *b, int n)
{
    uint8_t r[40];
    switch (b[1]) {
    case 0x00: {   // send frame: F1 00 id(4) bus len data
        if (n < 8 || !safety_ota_allowed()) return;   // read-only unless ignition off and contactors open
        can_frame_t f = {0};
        uint32_t id;
        memcpy(&id, &b[2], 4);
        f.ext = (id >> 31) & 1;
        f.id = id & 0x1FFFFFFF;
        uint8_t bus = b[6], len = b[7] & 0x0F;
        if (bus >= BUS_COUNT || len > 8 || n < 8 + len) return;
        f.dlc = len;
        memcpy(f.data, &b[8], len);
        can_send((bus_id_t)bus, &f);
        return;
    }
    case 0x01: {   // time sync
        uint32_t t = (uint32_t)esp_timer_get_time();
        r[0] = 0xF1; r[1] = 0x01;
        memcpy(&r[2], &t, 4);
        net_gvret_write(r, 6);
        return;
    }
    case 0x06:     // CAN0/CAN1 params
        r[0] = 0xF1; r[1] = 0x06;
        put_bus_params(&r[2], 0);
        put_bus_params(&r[7], 1);
        net_gvret_write(r, 12);
        return;
    case 0x07:     // device info
        r[0] = 0xF1; r[1] = 0x07; r[2] = 0x4D; r[3] = 0x01; r[4] = 0x20; r[5] = 0; r[6] = 0; r[7] = 0;
        net_gvret_write(r, 8);
        return;
    case 0x09:     // keepalive
        r[0] = 0xF1; r[1] = 0x09; r[2] = 0xDE; r[3] = 0xAD;
        net_gvret_write(r, 4);
        return;
    case 0x0C:     // number of buses
        r[0] = 0xF1; r[1] = 0x0C; r[2] = BUS_COUNT;
        net_gvret_write(r, 3);
        return;
    case 0x0D:     // extended buses 2..4
        r[0] = 0xF1; r[1] = 0x0D;
        put_bus_params(&r[2], 2);
        put_bus_params(&r[7], 3);
        memset(&r[12], 0, 5);
        net_gvret_write(r, 17);
        return;
    default:       // setup commands: accepted, buses are fixed at 500 kbit/s
        return;
    }
}

static void rx_commands(void)
{
    static uint8_t buf[64];
    static int len;
    int n = net_gvret_read(buf + len, sizeof(buf) - len);
    if (n <= 0) return;
    len += n;
    int i = 0;
    while (i < len) {
        if (buf[i] == 0xE7) { s_binary = true; i++; continue; }
        if (buf[i] != 0xF1) { i++; continue; }
        if (len - i < 2) break;
        int need = buf[i + 1] == 0x00 ? (len - i >= 8 ? 8 + (buf[i + 7] & 0x0F) : 64) : 2;
        if (len - i < need) break;
        handle_cmd(&buf[i], need);
        i += need;
    }
    memmove(buf, buf + i, len - i);
    len -= i;
}

// write a whole buffer: TCP can take part of it, so wait for room (up to ~20 ms), then give up on the rest
static void flush(const uint8_t *b, size_t len)
{
    size_t off = 0;
    for (int tries = 0; off < len && tries < 20; tries++) {
        int n = net_gvret_write(b + off, len - off);
        off += n;
        if (n == 0) vTaskDelay(1);
    }
    g_stats.gvret_bytes += off;
}

static void gvret_task(void *arg)
{
    static uint8_t out[1460];   // one TCP segment
    size_t used = 0;
    int64_t last_flush = esp_timer_get_time();
    for (;;) {
        rx_commands();
        can_frame_t f;
        int n = 0;
        while (n < 256 && canlog_pop(&f)) {
            if (used + 20 > sizeof(out)) {
                flush(out, used);
                used = 0;
                last_flush = esp_timer_get_time();
            }
            used += gvret_encode(&f, out + used);
            n++;
        }
        if (used && esp_timer_get_time() - last_flush > 5000) {
            flush(out, used);
            used = 0;
            last_flush = esp_timer_get_time();
        }
        if (n < 256) vTaskDelay(pdMS_TO_TICKS(2));
    }
}

void gvret_start(void)
{
    xTaskCreatePinnedToCore(gvret_task, "gvret", 4096, NULL, 6, NULL, 0);
    ESP_LOGI(TAG, "streaming all buses on TCP port 23");
}
