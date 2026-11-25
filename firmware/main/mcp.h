// CAN controller driver API (MCP2518FD on SPI; one instance per chip select).
#pragma once
#include <stdbool.h>
#include "can_types.h"

typedef void (*mcp_rx_cb_t)(int chip, const can_frame_t *f);

typedef struct {
    uint32_t rx, tx, rx_overflow, tx_queue_drop, errors, spi_us;
} mcp_stats_t;

bool mcp_init(int chip, bool listen_only);
bool mcp_set_listen_only(int chip, bool listen_only);   // CAN task only (touches SPI)
// any task: ask the CAN task to change mode on its next pass
void mcp_request_listen_only(int chip, bool listen_only);
void mcp_apply_pending(int chip);                          // CAN task
// service one chip once: drain up to a batch of frames from its receive FIFO and clear overflow flags.
// Calls cb for every received frame. Returns number of frames received.
int mcp_service(int chip, mcp_rx_cb_t cb);
// queue a frame for transmit (any task); actual loading happens in mcp_tx_pump() on the CAN task
bool mcp_queue_tx(int chip, const can_frame_t *f);
void mcp_tx_pump(int chip);
const mcp_stats_t *mcp_stats(int chip);
void mcp_stats_reset(void);
