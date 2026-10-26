/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef TAB5_GPIO_H
#define TAB5_GPIO_H
#include <stddef.h>

struct tab5_gpio_chip { char name[32]; char label[32]; unsigned lines; };
/* open_chip returns fd or -1/errno, request_line transfers an exclusive line fd.
 * Missing chip nodes use ENOENT/ENODEV; all callbacks follow libc errno rules. */
struct tab5_gpio_ops {
    int (*open_chip)(unsigned index, struct tab5_gpio_chip *info);
    int (*request_line)(int chip_fd, unsigned offset, int output, int initial);
    int (*get)(int line_fd);
    int (*set)(int line_fd, int value);
    int (*close)(int fd);
    int (*board_allowed)(void); /* 0 only for audited Tab5 board identity */
};
struct tab5_gpio { int fd; int output; const struct tab5_gpio_ops *ops; };
#define TAB5_GPIO_INITIALIZER {-1, 0, NULL}
extern const struct tab5_gpio_ops tab5_gpio_linux_ops;

int tab5_gpio_pin_allowed(unsigned pin);
/* Requires initializer; rejects opening over an already owned line with EBUSY.
 * mode and initial are 0/1; input requires initial=0. No pull/IRQ settings. */
int tab5_gpio_open(struct tab5_gpio *line, unsigned pin, int output, int initial);
int tab5_gpio_open_with_ops(struct tab5_gpio *line, unsigned pin, int output,
                           int initial, const struct tab5_gpio_ops *ops);
int tab5_gpio_get(struct tab5_gpio *line); /* value 0/1, or -1 with errno */
int tab5_gpio_set(struct tab5_gpio *line, int value); /* output only */
/* Idempotent. Ownership cleared before close, including close failure. */
int tab5_gpio_close(struct tab5_gpio *line);
#endif
