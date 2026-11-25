#include "net.h"

#include <string.h>
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "lwip/sockets.h"
#include "nvs.h"
#include "sdkconfig.h"

static volatile int s_client = -1;

#if CONFIG_ZE2_SIM
// QEMU has no Wi-Fi: the GVRET stream is encoded in full and handed to this sink, which only counts it.
static size_t s_sink;
void net_start(void) {}
bool net_gvret_connected(void) { return true; }
int net_gvret_write(const void *buf, size_t len)
{
    volatile const uint8_t *b = buf;
    s_sink += len + b[0];   // touch the data so the copy can't be optimised away
    return (int)len;
}
int net_gvret_read(void *buf, size_t len) { return 0; }
#else
static const char *TAG = "net";

static void server_task(void *arg)
{
    int ls = socket(AF_INET, SOCK_STREAM, IPPROTO_IP);
    struct sockaddr_in a = {.sin_family = AF_INET, .sin_port = htons(23), .sin_addr.s_addr = htonl(INADDR_ANY)};
    int yes = 1;
    setsockopt(ls, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));
    bind(ls, (struct sockaddr *)&a, sizeof(a));
    listen(ls, 1);
    for (;;) {
        int c = accept(ls, NULL, NULL);
        if (c < 0) continue;
        int nd = 1;
        setsockopt(c, IPPROTO_TCP, TCP_NODELAY, &nd, sizeof(nd));
        fcntl(c, F_SETFL, O_NONBLOCK);
        if (s_client >= 0) close(s_client);   // newest SavvyCAN wins
        s_client = c;
        ESP_LOGI(TAG, "GVRET client connected");
    }
}

bool net_gvret_connected(void) { return s_client >= 0; }

int net_gvret_write(const void *buf, size_t len)
{
    int c = s_client;
    if (c < 0) return (int)len;   // nobody listening: discard
    int n = send(c, buf, len, 0);
    if (n < 0 && errno != EAGAIN && errno != EWOULDBLOCK) {
        close(c);
        s_client = -1;
        return (int)len;
    }
    return n < 0 ? 0 : n;
}

int net_gvret_read(void *buf, size_t len)
{
    int c = s_client;
    if (c < 0) return 0;
    int n = recv(c, buf, len, 0);
    if (n == 0) { close(c); s_client = -1; }
    return n < 0 ? 0 : n;
}

void net_start(void)
{
    esp_netif_init();
    esp_event_loop_create_default();
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    esp_wifi_init(&cfg);
    char ssid[33] = "", pass[65] = "";
    nvs_handle_t h;
    if (nvs_open("wifi", NVS_READONLY, &h) == ESP_OK) {
        size_t l = sizeof(ssid);
        nvs_get_str(h, "ssid", ssid, &l);
        l = sizeof(pass);
        nvs_get_str(h, "pass", pass, &l);
        nvs_close(h);
    }
    if (ssid[0]) {
        esp_netif_create_default_wifi_sta();
        wifi_config_t wc = {0};
        strlcpy((char *)wc.sta.ssid, ssid, sizeof(wc.sta.ssid));
        strlcpy((char *)wc.sta.password, pass, sizeof(wc.sta.password));
        esp_wifi_set_mode(WIFI_MODE_STA);
        esp_wifi_set_config(WIFI_IF_STA, &wc);
        esp_wifi_start();
        esp_wifi_connect();
        ESP_LOGI(TAG, "station mode, joining %s", ssid);
    } else {
        esp_netif_create_default_wifi_ap();
        wifi_config_t wc = {.ap = {.channel = 6, .max_connection = 2, .authmode = WIFI_AUTH_WPA2_PSK}};
        strlcpy((char *)wc.ap.ssid, CONFIG_ZE2_WIFI_AP_SSID, sizeof(wc.ap.ssid));
        strlcpy((char *)wc.ap.password, CONFIG_ZE2_WIFI_AP_PASS, sizeof(wc.ap.password));
        wc.ap.ssid_len = strlen(CONFIG_ZE2_WIFI_AP_SSID);
        esp_wifi_set_mode(WIFI_MODE_AP);
        esp_wifi_set_config(WIFI_IF_AP, &wc);
        esp_wifi_start();
        ESP_LOGI(TAG, "access point %s (192.168.4.1)", CONFIG_ZE2_WIFI_AP_SSID);
    }
    esp_wifi_set_ps(WIFI_PS_NONE);
    xTaskCreatePinnedToCore(server_task, "gvret_srv", 3072, NULL, 5, NULL, 0);
}
#endif
