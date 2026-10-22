/* SPDX-License-Identifier: GPL-2.0-only */
/* Translate the Tab5 single-touch evdev stream into VT scrollback requests. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <linux/input.h>
#include <linux/tiocl.h>
#include <linux/vt.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

static int open_touch(void)
{
    char path[64], name[128];
    for (int n = 0; n < 32; n++) {
        snprintf(path, sizeof(path), "/dev/input/event%d", n);
        int fd = open(path, O_RDONLY | O_CLOEXEC);
        if (fd < 0) continue;
        memset(name, 0, sizeof(name));
        if (ioctl(fd, EVIOCGNAME(sizeof(name)), name) >= 0 &&
            strstr(name, "Tab5") && strstr(name, "Touch")) return fd;
        close(fd);
    }
    return -1;
}

/* The kernel ABI places the signed line count at the next 32-bit boundary. */
static int scroll_lines(int tty, int lines)
{
    struct vt_stat active;
    if (ioctl(tty, VT_GETSTATE, &active) < 0) return -1;
    if (active.v_active != 1) return 0;
    int request[2] = { TIOCL_SCROLLCONSOLE, lines };
    return ioctl(tty, TIOCLINUX, request);
}

int main(int argc, char **argv)
{
    if (argc == 3 && !strcmp(argv[1], "--lines")) {
        char *end;
        long lines = strtol(argv[2], &end, 10);
        if (!*argv[2] || *end || lines < -128 || lines > 128 || !lines) return 2;
        int tty = open("/dev/tty1", O_RDWR | O_CLOEXEC);
        if (tty < 0) return 1;
        int result = scroll_lines(tty, (int)lines);
        close(tty);
        return result < 0;
    }
    /* fbcon rotate:1: raw X increases towards screen bottom. */
    int axis = ABS_X, sign = 1, pixels = 32;
    if (argc > 1 && !strcmp(argv[1], "y")) axis = ABS_Y;
    else if (argc > 1 && strcmp(argv[1], "x")) return 2;
    if (argc > 2) {
        if (!strcmp(argv[2], "-1")) sign = -1;
        else if (strcmp(argv[2], "1")) return 2;
    }
    if (argc > 3) {
        char *end;
        long value = strtol(argv[3], &end, 10);
        if (*end || value < 4 || value > 256) return 2;
        pixels = (int)value;
    }
    int tty = open("/dev/tty1", O_RDWR | O_CLOEXEC);
    if (tty < 0) { perror("tty1"); return 1; }
    for (;;) {
        int fd = open_touch();
        if (fd < 0) { sleep(2); continue; }
        int down = 0, tracking = 0, position = 0, anchor = 0;
        struct input_event event;
        ssize_t length;
        for (;;) {
            length = read(fd, &event, sizeof(event));
            if (length < 0 && errno == EINTR) continue;
            if (length != (ssize_t)sizeof(event)) break;
            if (event.type == EV_ABS && event.code == axis) position = event.value;
            if (event.type == EV_KEY && event.code == BTN_TOUCH) down = event.value;
            if (event.type == EV_SYN && event.code == SYN_DROPPED) {
                /* Never turn lost events into a large accidental swipe. */
                down = tracking = 0;
                do { length = read(fd, &event, sizeof(event)); }
                while (length == (ssize_t)sizeof(event) &&
                       !(event.type == EV_SYN && event.code == SYN_REPORT));
                continue;
            }
            if (event.type != EV_SYN || event.code != SYN_REPORT) continue;
            if (!down) { tracking = 0; continue; }
            if (!tracking) { anchor = position; tracking = 1; continue; }
            int lines = (position - anchor) / pixels;
            if (lines) {
                /* Drag content down to reveal older output (negative lines). */
                if (scroll_lines(tty, -sign * lines) < 0) {
                    perror("VT scrollback"); close(fd); close(tty); return 1;
                }
                anchor += lines * pixels;
            }
        }
        close(fd);
        sleep(1);
    }
}
