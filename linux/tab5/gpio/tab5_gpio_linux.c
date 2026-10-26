/* SPDX-License-Identifier: GPL-2.0-only */
#define _GNU_SOURCE
#include "tab5_gpio.h"
#include <errno.h>
#include <fcntl.h>
#include <linux/gpio.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

#ifndef GPIO_V2_GET_LINE_IOCTL
#error "GPIO character device v2 headers are required"
#endif

static int chip_open(unsigned index, struct tab5_gpio_chip *info)
{
    char path[40];
    int length = snprintf(path, sizeof(path), "/dev/gpiochip%u", index);
    if (length < 0 || (size_t)length >= sizeof(path)) { errno = EINVAL; return -1; }
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return -1;
    struct gpiochip_info chip;
    memset(&chip, 0, sizeof(chip));
    if (ioctl(fd, GPIO_GET_CHIPINFO_IOCTL, &chip)) {
        int saved = errno; close(fd); errno = saved; return -1;
    }
    memcpy(info->name, chip.name, sizeof(info->name));
    memcpy(info->label, chip.label, sizeof(info->label));
    info->name[sizeof(info->name) - 1] = 0;
    info->label[sizeof(info->label) - 1] = 0;
    info->lines = chip.lines;
    return fd;
}

static int board_allowed(void)
{
    int fd = open("/proc/device-tree/compatible", O_RDONLY | O_CLOEXEC);
    if (fd < 0) return -1;
    char data[1024];
    ssize_t count = read(fd, data, sizeof(data));
    int saved = errno;
    if (close(fd)) return -1;
    if (count < 0) { errno = saved; return -1; }
    if (count == (ssize_t)sizeof(data)) { errno = EOVERFLOW; return -1; }
    size_t start = 0;
    while (start < (size_t)count) {
        size_t end = start;
        while (end < (size_t)count && data[end]) ++end;
        if (end == (size_t)count) break;
        if (end - start == sizeof("m5stack,tab5") - 1 &&
            !memcmp(data + start, "m5stack,tab5", sizeof("m5stack,tab5") - 1)) return 0;
        start = end + 1;
    }
    errno = ENODEV;
    return -1;
}

static int line_request(int chip_fd, unsigned offset, int output, int initial)
{
    struct gpio_v2_line_request request;
    memset(&request, 0, sizeof(request));
    request.offsets[0] = offset;
    request.num_lines = 1;
    memcpy(request.consumer, "tab5-userspace", sizeof("tab5-userspace"));
    request.config.flags = output ? GPIO_V2_LINE_FLAG_OUTPUT : GPIO_V2_LINE_FLAG_INPUT;
    if (output) {
        request.config.num_attrs = 1;
        request.config.attrs[0].attr.id = GPIO_V2_LINE_ATTR_ID_OUTPUT_VALUES;
        request.config.attrs[0].attr.values = (unsigned)initial;
        request.config.attrs[0].mask = 1;
    }
    if (ioctl(chip_fd, GPIO_V2_GET_LINE_IOCTL, &request)) return -1;
    return request.fd;
}

static int line_get(int fd)
{
    struct gpio_v2_line_values values;
    memset(&values, 0, sizeof(values));
    values.mask = 1;
    if (ioctl(fd, GPIO_V2_LINE_GET_VALUES_IOCTL, &values)) return -1;
    return (int)(values.bits & 1);
}

static int line_set(int fd, int value)
{
    struct gpio_v2_line_values values;
    memset(&values, 0, sizeof(values));
    values.mask = 1; values.bits = (unsigned)value;
    return ioctl(fd, GPIO_V2_LINE_SET_VALUES_IOCTL, &values);
}

const struct tab5_gpio_ops tab5_gpio_linux_ops = {
    chip_open, line_request, line_get, line_set, close, board_allowed
};
