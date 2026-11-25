#include "canlog.h"

#include <stdatomic.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "stats.h"

// Two rings so the CAN task never waits on a lock held by core 0:
//   s_can: CAN task only (lock-free single producer), ~110 ms of four saturated buses
//   s_app: frames sent from core-0 tasks (control loop, SavvyCAN), short spinlock between them
// The GVRET task is the single consumer of both.
typedef struct {
    can_frame_t *buf;
    unsigned len;
    atomic_uint head, tail;
} ring_t;

static can_frame_t s_can_buf[2048], s_app_buf[128];
static ring_t s_can = {.buf = s_can_buf, .len = 2048}, s_app = {.buf = s_app_buf, .len = 128};
static portMUX_TYPE s_app_lock = portMUX_INITIALIZER_UNLOCKED;
static TaskHandle_t s_can_task;

void canlog_set_can_task(void *t) { s_can_task = t; }

static bool push(ring_t *r, const can_frame_t *f)
{
    unsigned h = atomic_load_explicit(&r->head, memory_order_relaxed);
    unsigned next = (h + 1) % r->len;
    if (next == atomic_load_explicit(&r->tail, memory_order_acquire)) return false;
    r->buf[h] = *f;
    atomic_store_explicit(&r->head, next, memory_order_release);
    return true;
}

static bool pop(ring_t *r, can_frame_t *f)
{
    unsigned t = atomic_load_explicit(&r->tail, memory_order_relaxed);
    if (t == atomic_load_explicit(&r->head, memory_order_acquire)) return false;
    *f = r->buf[t];
    atomic_store_explicit(&r->tail, (t + 1) % r->len, memory_order_release);
    return true;
}

void canlog_push(const can_frame_t *f)
{
    bool ok;
    if (xTaskGetCurrentTaskHandle() == s_can_task) {
        ok = push(&s_can, f);
    } else {
        taskENTER_CRITICAL(&s_app_lock);
        ok = push(&s_app, f);
        taskEXIT_CRITICAL(&s_app_lock);
    }
    if (!ok) g_stats.log_drop++;
}

bool canlog_pop(can_frame_t *f) { return pop(&s_can, f) || pop(&s_app, f); }
