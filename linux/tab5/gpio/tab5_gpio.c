/* SPDX-License-Identifier: GPL-2.0-only */
#include "tab5_gpio.h"
#include <errno.h>
#include <string.h>

int tab5_gpio_pin_allowed(unsigned pin)
{
    switch (pin) {
    case 2: case 3: case 4: case 5: case 16: case 18:
    case 47: case 48: case 45: case 51: return 1;
    default: return 0;
    }
}

static int fail(int error) { errno = error; return -1; }

static int chip_name_valid(const char *name)
{
    if (strncmp(name, "gpiochip", 8) || name[8] < '0' || name[8] > '9') return 0;
    for (unsigned i = 8; i < 32; ++i) {
        if (!name[i]) return 1;
        if (name[i] < '0' || name[i] > '9') return 0;
    }
    return 0;
}

int tab5_gpio_open_with_ops(struct tab5_gpio *line, unsigned pin, int output,
                           int initial, const struct tab5_gpio_ops *ops)
{
    if (!line || !ops || !ops->open_chip || !ops->request_line ||
        !ops->get || !ops->set || !ops->close || !ops->board_allowed) return fail(EINVAL);
    if (line->fd >= 0) return fail(EBUSY);
    if ((output != 0 && output != 1) || (initial != 0 && initial != 1) ||
        (!output && initial)) return fail(EINVAL);
    if (!tab5_gpio_pin_allowed(pin)) return fail(EPERM);
    if (ops->board_allowed()) return -1;
    /* Mapping resolved from controller identity, never gpiochip enumeration. */
    int selected = -1;
    unsigned offset = pin % 32;
    for (unsigned i = 0; i < 256; ++i) {
        struct tab5_gpio_chip info;
        memset(&info, 0, sizeof(info));
        int fd = ops->open_chip(i, &info);
        if (fd < 0) {
            if (errno == ENOENT || errno == ENODEV) continue;
            int saved = errno;
            if (selected >= 0) ops->close(selected);
            return fail(saved);
        }
        /* Stable labels are installed by this repository's audited driver patch.
         * Legacy ambiguous labels are deliberately rejected. */
        const char *label = pin < 32 ? "esp32p4-gpio-bank0" : "esp32p4-gpio-bank1";
        int matches = chip_name_valid(info.name) && info.lines == (pin < 32 ? 32u : 23u) &&
            !strncmp(info.label, label, sizeof(info.label));
        if (matches) {
            if (selected >= 0) {
                ops->close(fd); ops->close(selected); return fail(EEXIST);
            }
            selected = fd;
        } else if (ops->close(fd)) {
            int saved = errno;
            if (selected >= 0) ops->close(selected);
            return fail(saved);
        }
    }
    if (selected < 0) return fail(ENODEV);
    int fd = ops->request_line(selected, offset, output, initial);
    int saved = errno;
    if (ops->close(selected)) {
        int close_error = errno;
        if (fd >= 0) ops->close(fd);
        return fail(close_error);
    }
    if (fd < 0) return fail(saved);
    line->fd = fd; line->output = output; line->ops = ops;
    return 0;
}

int tab5_gpio_open(struct tab5_gpio *line, unsigned pin, int output, int initial)
{
    return tab5_gpio_open_with_ops(line, pin, output, initial, &tab5_gpio_linux_ops);
}

int tab5_gpio_get(struct tab5_gpio *line)
{
    if (!line || line->fd < 0 || !line->ops) return fail(EBADF);
    int result = line->ops->get(line->fd);
    if (result != -1 && result != 0 && result != 1) return fail(EIO);
    return result;
}

int tab5_gpio_set(struct tab5_gpio *line, int value)
{
    if (value != 0 && value != 1) return fail(EINVAL);
    if (!line || line->fd < 0 || !line->ops) return fail(EBADF);
    if (!line->output) return fail(EPERM);
    return line->ops->set(line->fd, value);
}

int tab5_gpio_close(struct tab5_gpio *line)
{
    if (!line) return fail(EINVAL);
    if (line->fd < 0) return 0;
    int fd = line->fd;
    const struct tab5_gpio_ops *ops = line->ops;
    line->fd = -1; line->ops = NULL; line->output = 0;
    if (!ops || !ops->close) return fail(EINVAL);
    return ops->close(fd);
}
