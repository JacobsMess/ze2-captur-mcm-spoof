// Ring of every frame seen or sent. Producers: CAN task (core 1) and control task (TX, core 0), under a short
// spinlock; single consumer: the GVRET task (core 0).
#pragma once
#include <stdbool.h>
#include "can_types.h"

void canlog_set_can_task(void *task);      // the CAN task gets a lock-free ring of its own
void canlog_push(const can_frame_t *f);   // never blocks; drops (counted) when full
bool canlog_pop(can_frame_t *f);
