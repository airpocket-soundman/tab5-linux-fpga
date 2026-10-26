/* SPDX-License-Identifier: GPL-2.0-only */
#define _GNU_SOURCE
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/gpio.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>
#include "tab5_gpio.h"

static int mock_open(const char *, int, ...);
static ssize_t mock_read(int, void *, size_t);
static int mock_ioctl(int, unsigned long, ...);
static int mock_close(int);
#define open mock_open
#define read mock_read
#define ioctl mock_ioctl
#define close mock_close
#include "tab5_gpio_linux.c"
#undef open
#undef read
#undef ioctl
#undef close

static unsigned open_calls, read_calls, ioctl_calls, close_calls;
static int open_error, read_error, ioctl_error, close_error;
static int last_closed, last_ioctl_fd;
static unsigned long last_ioctl_request;
static char last_path[80];
static const char *compatible;
static size_t compatible_size;
static struct gpiochip_info chip_reply;
static struct gpio_v2_line_request captured_request;
static struct gpio_v2_line_values captured_values;
static unsigned long long read_bits;

static void reset(void)
{
    open_calls = read_calls = ioctl_calls = close_calls = 0;
    open_error = read_error = ioctl_error = close_error = 0;
    last_closed = last_ioctl_fd = -1;
    compatible = "m5stack,tab5"; compatible_size = sizeof("m5stack,tab5");
    memset(&chip_reply, 0, sizeof(chip_reply));
    strcpy(chip_reply.name, "gpiochip42");
    strcpy(chip_reply.label, "esp32p4-gpio-bank1");
    chip_reply.lines = 23;
    memset(&captured_request, 0xa5, sizeof(captured_request));
    memset(&captured_values, 0xa5, sizeof(captured_values));
    read_bits = 0;
}

static int mock_open(const char *path, int flags, ...)
{
    ++open_calls;
    assert(flags == (O_RDONLY | O_CLOEXEC));
    assert(strlen(path) < sizeof(last_path));
    strcpy(last_path, path);
    if (open_error) { errno = open_error; return -1; }
    if (!strcmp(path, "/proc/device-tree/compatible")) return 11;
    assert(!strncmp(path, "/dev/gpiochip", strlen("/dev/gpiochip")));
    return 22;
}

static ssize_t mock_read(int fd, void *data, size_t size)
{
    assert(fd == 11 && size == 1024);
    ++read_calls;
    if (read_error) { errno = read_error; return -1; }
    size_t count = compatible_size < size ? compatible_size : size;
    memcpy(data, compatible, count);
    return (ssize_t)count;
}

static int mock_ioctl(int fd, unsigned long request, ...)
{
    va_list args;
    va_start(args, request);
    void *data = va_arg(args, void *);
    va_end(args);
    ++ioctl_calls; last_ioctl_fd = fd; last_ioctl_request = request;
    if (ioctl_error) { errno = ioctl_error; return -1; }
    if (request == GPIO_GET_CHIPINFO_IOCTL) {
        assert(fd == 22);
        memcpy(data, &chip_reply, sizeof(chip_reply));
    } else if (request == GPIO_V2_GET_LINE_IOCTL) {
        assert(fd == 22);
        captured_request = *(struct gpio_v2_line_request *)data;
        ((struct gpio_v2_line_request *)data)->fd = 77;
    } else if (request == GPIO_V2_LINE_GET_VALUES_IOCTL) {
        assert(fd == 77);
        captured_values = *(struct gpio_v2_line_values *)data;
        ((struct gpio_v2_line_values *)data)->bits = read_bits;
    } else {
        assert(request == GPIO_V2_LINE_SET_VALUES_IOCTL && fd == 77);
        captured_values = *(struct gpio_v2_line_values *)data;
    }
    return 0;
}

static int mock_close(int fd)
{
    assert(fd == 11 || fd == 22 || fd == 77);
    ++close_calls; last_closed = fd;
    if (close_error) { errno = close_error; return -1; }
    return 0;
}

int main(void)
{
    reset(); assert(board_allowed() == 0);
    assert(open_calls == 1 && read_calls == 1 && close_calls == 1 && ioctl_calls == 0);
    assert(!strcmp(last_path, "/proc/device-tree/compatible"));
    static const char multi[] = "espressif,esp32p4\0m5stack,tab5\0other\0";
    compatible = multi; compatible_size = sizeof(multi);
    assert(board_allowed() == 0);
    const char *invalid[] = {"", "m5stack,tab5x", "xm5stack,tab5", "espressif,esp32p4", "m5stack,tab"};
    for (unsigned i = 0; i < sizeof(invalid) / sizeof(invalid[0]); ++i) {
        reset(); compatible = invalid[i]; compatible_size = strlen(invalid[i]) + 1;
        assert(board_allowed() == -1 && errno == ENODEV && close_calls == 1);
    }
    reset(); compatible_size = strlen(compatible); /* Correct text without NUL is rejected. */
    assert(board_allowed() == -1 && errno == ENODEV);
    reset(); compatible_size = 0;
    assert(board_allowed() == -1 && errno == ENODEV);
    static char oversized[1024]; memset(oversized, 'x', sizeof(oversized));
    reset(); compatible = oversized; compatible_size = sizeof(oversized);
    assert(board_allowed() == -1 && errno == EOVERFLOW && close_calls == 1);
    reset(); open_error = EACCES;
    assert(board_allowed() == -1 && errno == EACCES && read_calls == 0 && close_calls == 0);
    reset(); read_error = EINTR;
    assert(board_allowed() == -1 && errno == EINTR && close_calls == 1);
    reset(); close_error = EIO;
    assert(board_allowed() == -1 && errno == EIO);

    struct tab5_gpio_chip info;
    reset(); assert(chip_open(91, &info) == 22);
    assert(!strcmp(last_path, "/dev/gpiochip91") && close_calls == 0);
    assert(!strcmp(info.name, "gpiochip42") && !strcmp(info.label, "esp32p4-gpio-bank1") && info.lines == 23);
    assert(last_ioctl_fd == 22 && last_ioctl_request == GPIO_GET_CHIPINFO_IOCTL);
    reset(); memset(chip_reply.name, 'n', sizeof(chip_reply.name));
    memset(chip_reply.label, 'l', sizeof(chip_reply.label));
    assert(chip_open(0, &info) == 22);
    assert(info.name[31] == 0 && info.label[31] == 0);
    for (unsigned i = 0; i < 31; ++i) assert(info.name[i] == 'n' && info.label[i] == 'l');
    reset(); open_error = ENOENT;
    assert(chip_open(9, &info) == -1 && errno == ENOENT && ioctl_calls == 0 && close_calls == 0);
    reset(); ioctl_error = ENOTTY; close_error = EIO;
    assert(chip_open(9, &info) == -1 && errno == ENOTTY && close_calls == 1 && last_closed == 22);

    reset(); assert(line_request(22, 19, 0, 0) == 77);
    assert(captured_request.offsets[0] == 19 && captured_request.num_lines == 1);
    assert(captured_request.config.flags == GPIO_V2_LINE_FLAG_INPUT && captured_request.config.num_attrs == 0);
    assert(!strcmp(captured_request.consumer, "tab5-userspace"));
    assert(captured_request.event_buffer_size == 0);
    for (int initial = 0; initial <= 1; ++initial) {
        reset(); assert(line_request(22, 16, 1, initial) == 77);
        assert(captured_request.config.flags == GPIO_V2_LINE_FLAG_OUTPUT);
        assert(captured_request.config.num_attrs == 1);
        assert(captured_request.config.attrs[0].attr.id == GPIO_V2_LINE_ATTR_ID_OUTPUT_VALUES);
        assert(captured_request.config.attrs[0].attr.values == (unsigned)initial);
        assert(captured_request.config.attrs[0].mask == 1);
        assert(ioctl_calls == 1 && last_ioctl_request == GPIO_V2_GET_LINE_IOCTL && close_calls == 0);
    }
    reset(); ioctl_error = EBUSY;
    assert(line_request(22, 16, 1, 0) == -1 && errno == EBUSY && close_calls == 0);
    for (unsigned value = 0; value <= 3; ++value) {
        reset(); read_bits = value;
        assert(line_get(77) == (int)(value & 1));
        assert(captured_values.mask == 1 && captured_values.bits == 0);
        assert(last_ioctl_request == GPIO_V2_LINE_GET_VALUES_IOCTL);
    }
    for (int value = 0; value <= 1; ++value) {
        reset(); assert(line_set(77, value) == 0);
        assert(captured_values.mask == 1 && captured_values.bits == (unsigned)value);
        assert(last_ioctl_request == GPIO_V2_LINE_SET_VALUES_IOCTL);
    }
    reset(); ioctl_error = EIO;
    assert(line_get(77) == -1 && errno == EIO);
    assert(line_set(77, 1) == -1 && errno == EIO && close_calls == 0);
    reset(); assert(tab5_gpio_linux_ops.close(77) == 0 && close_calls == 1);
    puts("PASS: Linux adapter board parsing, chip metadata, GPIO v2 ioctls and error cleanup (all syscalls mocked)");
    return 0;
}
