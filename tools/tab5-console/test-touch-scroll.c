/* SPDX-License-Identifier: GPL-2.0-only */
/* Linux host scenarios against the actual daemon, with evdev/VT syscalls mocked.
 * cc -std=c11 -Wall -Wextra -Werror test-touch-scroll.c -o test-touch-scroll
 */
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <linux/input.h>
#include <linux/tiocl.h>
#include <linux/vt.h>
#include <setjmp.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

static int mock_open(const char *, int, ...);
static int mock_close(int);
static int mock_ioctl(int, unsigned long, ...);
static ssize_t mock_read(int, void *, size_t);
static unsigned int mock_sleep(unsigned int);
#define open mock_open
#define close mock_close
#define ioctl mock_ioctl
#define read mock_read
#define sleep mock_sleep
#define main daemon_main
#include "tab5-touch-scroll.c"
#undef main
#undef open
#undef close
#undef ioctl
#undef read
#undef sleep

#define E(t, c, v) { .type = (t), .code = (c), .value = (v) }
#define SYNC E(EV_SYN, SYN_REPORT, 0)
#define INTERRUPTED E(0xffff, 0, 0)
static jmp_buf finished;
static const struct input_event *events;
static size_t event_count, event_index;
static int positions[4], seed_count, fail_first_seed;
static int scrolls[16], scroll_count, closes, sleeps;

static int mock_open(const char *path, int flags, ...)
{
    (void)flags;
    if (!strcmp(path, "/dev/tty1")) return 3;
    if (!strcmp(path, "/dev/input/event0")) return 4;
    errno = ENOENT;
    return -1;
}

static int mock_close(int fd)
{
    assert(fd == 3 || fd == 4);
    if (fd == 4) closes++;
    return 0;
}

static int mock_ioctl(int fd, unsigned long request, ...)
{
    va_list args;
    va_start(args, request);
    void *argument = va_arg(args, void *);
    va_end(args);
    if (fd == 4 && request == EVIOCGNAME(128)) {
        strcpy(argument, "Tab5 ST712x Touchscreen");
        return 0;
    }
    if (fd == 4 && request == EVIOCGABS(ABS_X)) {
        assert(seed_count < 4);
        int index = seed_count++;
        if (fail_first_seed && !index) { errno = EIO; return -1; }
        ((struct input_absinfo *)argument)->value = positions[index];
        return 0;
    }
    assert(fd == 3);
    if (request == VT_GETSTATE) {
        ((struct vt_stat *)argument)->v_active = 1;
        return 0;
    }
    assert(request == TIOCLINUX);
    int *lines = argument;
    assert(lines[0] == TIOCL_SCROLLCONSOLE);
    assert(scroll_count < 16);
    scrolls[scroll_count++] = lines[1];
    return 0;
}

static ssize_t mock_read(int fd, void *buffer, size_t count)
{
    assert(fd == 4 && count == sizeof(struct input_event));
    if (event_index == event_count) longjmp(finished, 1);
    const struct input_event *event = &events[event_index++];
    if (event->type == 0xffff) { errno = EINTR; return -1; }
    memcpy(buffer, event, count);
    return (ssize_t)count;
}

static unsigned int mock_sleep(unsigned int seconds)
{
    (void)seconds;
    sleeps++;
    return 0;
}

static void run(const struct input_event *stream, size_t count, int first, int second, int fail)
{
    events = stream; event_count = count; event_index = 0;
    positions[0] = first; positions[1] = second;
    seed_count = scroll_count = closes = sleeps = 0;
    fail_first_seed = fail;
    char *argv[] = { "tab5-touch-scroll", NULL };
    if (!setjmp(finished)) { daemon_main(1, argv); assert(!"daemon unexpectedly exited"); }
}

int main(void)
{
    /* A new contact can omit unchanged ABS_X: a small move is one line. */
    const struct input_event same_coordinate[] = {
        E(EV_KEY, BTN_TOUCH, 1), SYNC, E(EV_ABS, ABS_X, 328), SYNC,
        E(EV_ABS, ABS_X, 352), SYNC,
    };
    run(same_coordinate, sizeof(same_coordinate) / sizeof(*same_coordinate), 320, 320, 0);
    assert(seed_count == 1 && scroll_count == 1 && scrolls[0] == -1);

    /* Lost events (including an interrupted discard read) cannot become a swipe. */
    const struct input_event dropped[] = {
        E(EV_KEY, BTN_TOUCH, 1), SYNC, E(EV_SYN, SYN_DROPPED, 0),
        INTERRUPTED, E(EV_ABS, ABS_X, 5000), SYNC,
        E(EV_KEY, BTN_TOUCH, 0), SYNC, E(EV_KEY, BTN_TOUCH, 1), SYNC,
        E(EV_ABS, ABS_X, 672), SYNC,
    };
    run(dropped, sizeof(dropped) / sizeof(*dropped), 400, 640, 0);
    assert(seed_count == 2 && scroll_count == 1 && scrolls[0] == -1);

    /* Discontinuous input cannot overflow arithmetic or create an unbounded ioctl. */
    const struct input_event discontinuous[] = {
        E(EV_KEY, BTN_TOUCH, 1), SYNC, E(EV_ABS, ABS_X, INT_MAX), SYNC,
        E(EV_ABS, ABS_X, INT_MIN), SYNC,
    };
    run(discontinuous, sizeof(discontinuous) / sizeof(*discontinuous), 0, 0, 0);
    assert(scroll_count == 2 && scrolls[0] == -128 && scrolls[1] == 128);

    /* Failed state queries close the fd, wait, reopen, then seed the next contact. */
    run(same_coordinate, sizeof(same_coordinate) / sizeof(*same_coordinate), 0, 320, 1);
    assert(seed_count == 2 && closes == 1 && sleeps == 1);
    assert(scroll_count == 1 && scrolls[0] == -1);
    puts("touch-scroll scenarios passed");
    return 0;
}
