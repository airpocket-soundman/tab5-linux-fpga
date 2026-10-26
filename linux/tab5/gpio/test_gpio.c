/* SPDX-License-Identifier: GPL-2.0-only */
#include "tab5_gpio.h"
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>

static unsigned opens, closes, requests, sets, get_calls, guards;
static unsigned requested_offset;
static int requested_chip, requested_output, requested_initial;
static int mode, request_error, close_error, read_value, set_error, board_error;
static int chip_open(unsigned index, struct tab5_gpio_chip *info)
{
    ++opens;
    if (index != 3 && index != 7 && !(mode == 1 && index == 8)) {
        errno = ENOENT; return -1;
    }
    memset(info, 0, sizeof(*info));
    strcpy(info->name, index == 3 ? "gpiochip91" : "gpiochip42");
    strcpy(info->label, index == 3 ? "esp32p4-gpio-bank0" : "esp32p4-gpio-bank1");
    info->lines = index == 3 ? 32 : 23;
    if (mode == 2) info->lines = 31;
    if (mode == 3) strcpy(info->label, "500e0000.gpio");
    if (mode == 4) strcpy(info->name, "unrelated");
    return 100 + (int)index;
}
static int request_line(int fd, unsigned offset, int output, int initial)
{
    ++requests;
    requested_chip = fd; requested_offset = offset;
    requested_output = output; requested_initial = initial;
    if (request_error) { errno = request_error; return -1; }
    return 700;
}
static int get(int fd) { assert(fd == 700); ++get_calls; return read_value; }
static int set(int fd, int value)
{
    assert(fd == 700 && (value == 0 || value == 1)); ++sets;
    if (set_error) { errno = set_error; return -1; }
    return 0;
}
static int release(int fd)
{
    ++closes;
    if (fd == close_error) { errno = EIO; return -1; }
    return 0;
}
static int board(void)
{
    ++guards;
    if (board_error) { errno = board_error; return -1; }
    return 0;
}
const struct tab5_gpio_ops tab5_gpio_linux_ops = {
    chip_open, request_line, get, set, release, board
};
static void reset(void)
{
    opens = closes = requests = sets = get_calls = guards = 0;
    mode = request_error = close_error = read_value = set_error = board_error = 0;
}

int main(void)
{
    for (unsigned pin = 0; pin < 100; ++pin) {
        int expected = pin == 2 || pin == 3 || pin == 4 || pin == 5 || pin == 16 ||
            pin == 18 || pin == 45 || pin == 47 || pin == 48 || pin == 51;
        assert(tab5_gpio_pin_allowed(pin) == expected);
        reset(); struct tab5_gpio line = TAB5_GPIO_INITIALIZER;
        int result = tab5_gpio_open(&line, pin, 1, 1);
        if (expected) {
            assert(result == 0 && requests == 1 && line.fd == 700);
            assert(requested_chip == (pin < 32 ? 103 : 107));
            assert(requested_offset == pin % 32 && requested_output == 1 && requested_initial == 1);
            assert(tab5_gpio_close(&line) == 0);
        } else assert(result == -1 && errno == EPERM && opens == 0 && guards == 0);
    }
    reset(); struct tab5_gpio line = TAB5_GPIO_INITIALIZER;
    assert(tab5_gpio_open(&line, 16, 2, 0) == -1 && errno == EINVAL);
    assert(tab5_gpio_open(&line, 16, 1, -1) == -1 && errno == EINVAL);
    assert(tab5_gpio_open(&line, 16, 0, 1) == -1 && errno == EINVAL);
    assert(opens == 0 && guards == 0);
    board_error = ENODEV;
    assert(tab5_gpio_open(&line, 16, 0, 0) == -1 && errno == ENODEV && opens == 0);
    reset(); assert(tab5_gpio_open(&line, 16, 0, 0) == 0);
    unsigned before = opens;
    assert(tab5_gpio_open(&line, 18, 1, 0) == -1 && errno == EBUSY && opens == before);
    assert(tab5_gpio_set(&line, 1) == -1 && errno == EPERM && sets == 0);
    assert(tab5_gpio_set(&line, 2) == -1 && errno == EINVAL && sets == 0);
    read_value = 1; assert(tab5_gpio_get(&line) == 1);
    read_value = 7; assert(tab5_gpio_get(&line) == -1 && errno == EIO);
    assert(tab5_gpio_close(&line) == 0);
    unsigned previous = closes;
    assert(tab5_gpio_close(&line) == 0 && closes == previous);
    assert(tab5_gpio_get(&line) == -1 && errno == EBADF);
    assert(tab5_gpio_set(&line, 0) == -1 && errno == EBADF);
    reset(); assert(tab5_gpio_open(&line, 51, 1, 0) == 0);
    set_error = EIO; assert(tab5_gpio_set(&line, 1) == -1 && errno == EIO);
    close_error = 700;
    assert(tab5_gpio_close(&line) == -1 && errno == EIO && line.fd == -1);
    previous = closes; assert(tab5_gpio_close(&line) == 0 && closes == previous);
    reset(); request_error = EBUSY;
    assert(tab5_gpio_open(&line, 48, 1, 1) == -1 && errno == EBUSY && line.fd == -1);
    assert(requests == 1 && closes == 2);
    for (int variant = 1; variant <= 4; ++variant) {
        reset(); mode = variant;
        assert(tab5_gpio_open(&line, 51, 1, 1) == -1);
        assert(errno == (variant == 1 ? EEXIST : ENODEV) && requests == 0 && line.fd == -1);
    }
    reset(); close_error = 107;
    assert(tab5_gpio_open(&line, 48, 1, 0) == -1 && errno == EIO && line.fd == -1);
    assert(requests == 1 && closes == 3); /* selected + line cleanup + other chip */
    puts("PASS: policy, mapping, pre-I/O validation, exclusive lifetime, error cleanup (mock only)");
    return 0;
}
