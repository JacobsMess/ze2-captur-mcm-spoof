// Stage 2 (MCM removed): pass the Captur pack summary to the ZombieVerter on the EV bus.
#pragma once
#include <stdbool.h>
#include <stdint.h>

void zombie_tick(uint32_t now_ms, bool stage2);
