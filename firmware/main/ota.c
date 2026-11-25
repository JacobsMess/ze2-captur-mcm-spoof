#include "ota.h"

#include <stdio.h>
#include "captur.h"
#include "contactors.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_ota_ops.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "gateway.h"
#include "safety.h"
#include "sdkconfig.h"
#include "stats.h"

static const char *TAG = "ota";

#if !CONFIG_ZE2_SIM
static esp_err_t status_get(httpd_req_t *req)
{
    char b[512];
    snprintf(b, sizeof(b),
             "{\"safety\":%d,\"reason\":\"%s\",\"contactors\":%d,\"gateway\":%d,\"soc\":%.1f,"
             "\"cell_min\":%u,\"cell_max\":%u,\"t_min\":%d,\"t_max\":%d,\"rx\":[%lu,%lu,%lu,%lu],"
             "\"log_drop\":%lu,\"ota_allowed\":%s}",
             g_safety.level, g_safety.reason, contactors_state(), gateway_state(), g_pack.soc_pct,
             g_pack.cell_min_mv, g_pack.cell_max_mv, g_pack.temp_min_c, g_pack.temp_max_c,
             (unsigned long)g_stats.rx[0], (unsigned long)g_stats.rx[1], (unsigned long)g_stats.rx[2],
             (unsigned long)g_stats.rx[3], (unsigned long)g_stats.log_drop, safety_ota_allowed() ? "true" : "false");
    httpd_resp_set_type(req, "application/json");
    return httpd_resp_sendstr(req, b);
}

static esp_err_t update_post(httpd_req_t *req)
{
    if (!safety_ota_allowed()) {
        httpd_resp_set_status(req, "409 Conflict");
        return httpd_resp_sendstr(req, "refused: switch the ignition off (contactors must be open)\n");
    }
    const esp_partition_t *part = esp_ota_get_next_update_partition(NULL);
    esp_ota_handle_t h;
    if (!part || esp_ota_begin(part, OTA_WITH_SEQUENTIAL_WRITES, &h) != ESP_OK) {
        httpd_resp_send_500(req);
        return ESP_FAIL;
    }
    static char buf[2048];
    int left = req->content_len;
    while (left > 0) {
        if (!safety_ota_allowed()) {   // ignition switched on mid-update: abandon, old image stays
            esp_ota_abort(h);
            httpd_resp_set_status(req, "409 Conflict");
            return httpd_resp_sendstr(req, "aborted: ignition on\n");
        }
        int n = httpd_req_recv(req, buf, left < (int)sizeof(buf) ? left : (int)sizeof(buf));
        if (n == HTTPD_SOCK_ERR_TIMEOUT) continue;
        if (n <= 0 || esp_ota_write(h, buf, n) != ESP_OK) {
            esp_ota_abort(h);
            httpd_resp_send_500(req);
            return ESP_FAIL;
        }
        left -= n;
    }
    if (esp_ota_end(h) != ESP_OK || esp_ota_set_boot_partition(part) != ESP_OK) {
        httpd_resp_send_500(req);
        return ESP_FAIL;
    }
    httpd_resp_sendstr(req, "ok, rebooting into the new image (probation, auto-rollback)\n");
    ESP_LOGW(TAG, "update written to %s, rebooting", part->label);
    vTaskDelay(pdMS_TO_TICKS(500));
    esp_restart();
    return ESP_OK;
}
#endif

void ota_start(void)
{
#if !CONFIG_ZE2_SIM
    httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
    cfg.core_id = 0;
    cfg.recv_wait_timeout = 10;
    httpd_handle_t s;
    if (httpd_start(&s, &cfg) != ESP_OK) return;
    httpd_uri_t st = {.uri = "/", .method = HTTP_GET, .handler = status_get};
    httpd_uri_t up = {.uri = "/update", .method = HTTP_POST, .handler = update_post};
    httpd_register_uri_handler(s, &st);
    httpd_register_uri_handler(s, &up);
#endif
}

void ota_tick(uint32_t now_ms, bool healthy)
{
    static bool done;
    if (done) return;
    esp_ota_img_states_t state;
    const esp_partition_t *run = esp_ota_get_running_partition();
    if (esp_ota_get_state_partition(run, &state) != ESP_OK || state != ESP_OTA_IMG_PENDING_VERIFY) {
        done = true;
        return;
    }
    if (!healthy && now_ms > 10000) {
        ESP_LOGE(TAG, "new image unhealthy: rolling back");
        esp_ota_mark_app_invalid_rollback_and_reboot();
    }
    if (healthy && now_ms > OTA_PROBATION_S * 1000) {
        esp_ota_mark_app_valid_cancel_rollback();
        ESP_LOGI(TAG, "new image confirmed");
        done = true;
    }
}
