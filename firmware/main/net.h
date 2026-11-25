// Wi-Fi (soft AP, or station if credentials are stored in NVS) and the GVRET TCP socket (port 23) that
// SavvyCAN connects to as a "Network connection (GVRET)" device.
#pragma once
#include <stddef.h>
#include <stdbool.h>

void net_start(void);
bool net_gvret_connected(void);
int net_gvret_write(const void *buf, size_t len);   // non-blocking; returns bytes accepted
int net_gvret_read(void *buf, size_t len);          // non-blocking
