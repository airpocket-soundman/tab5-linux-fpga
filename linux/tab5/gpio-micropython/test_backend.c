/* SPDX-License-Identifier: GPL-2.0-only */
/* Compile-time test backend. Never linked with production Linux adapter. */
#include "tab5_gpio.h"
#include <errno.h>
#include <stdio.h>
#include <string.h>
#if !TAB5_GPIO_TEST_BACKEND
#error "test backend requires explicit host test build"
#endif
static unsigned counters[4]; /* chip opens, line requests, line closes, active */
static unsigned char owned[57], values[57];
static int fail_close;
static int bad(int error) { errno = error; return -1; }
static int mock_board(void) { return 0; }
static int mock_open(unsigned index, struct tab5_gpio_chip *info) {
    ++counters[0];
    if (index > 1) return bad(ENOENT);
    snprintf(info->name, sizeof(info->name), "gpiochip%u", index);
    snprintf(info->label, sizeof(info->label), "esp32p4-gpio-bank%u", index);
    info->lines = index ? 23 : 32;
    return (int)(100 + index);
}
static int mock_request(int fd, unsigned offset, int output, int initial) {
    (void)output;
    ++counters[1];
    if (fd < 100 || fd > 101 || offset >= (fd == 100 ? 32u : 23u)) return bad(EINVAL);
    unsigned pin = (unsigned)(fd - 100) * 32 + offset;
    if (owned[pin]) return bad(EBUSY);
    owned[pin] = 1; values[pin] = (unsigned char)initial; ++counters[3];
    return (int)(1000 + pin); /* Deliberately reuses a released descriptor. */
}
static int mock_get(int fd) {
    if (fd < 1000 || fd >= 1057 || !owned[fd - 1000]) return bad(EBADF);
    return values[fd - 1000];
}
static int mock_set(int fd, int value) {
    if (mock_get(fd) < 0) return -1;
    values[fd - 1000] = (unsigned char)value; return 0;
}
static int mock_close(int fd) {
    if (fd == 100 || fd == 101) return 0;
    ++counters[2];
    if (fd < 1000 || fd >= 1057 || !owned[fd - 1000]) return bad(EBADF);
    owned[fd - 1000] = 0; --counters[3];
    if (fail_close) { fail_close = 0; return bad(EINTR); }
    return 0;
}
const struct tab5_gpio_ops tab5_gpio_linux_ops = {
    mock_open, mock_request, mock_get, mock_set, mock_close, mock_board,
};
void tab5_gpio_test_stats(unsigned out[4]) { memcpy(out, counters, sizeof(counters)); }
void tab5_gpio_test_fail_close(void) { fail_close = 1; }
