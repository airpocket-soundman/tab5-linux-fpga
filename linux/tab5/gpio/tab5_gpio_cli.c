/* SPDX-License-Identifier: GPL-2.0-only */
#define _POSIX_C_SOURCE 200809L
#include "tab5_gpio.h"
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

static volatile sig_atomic_t interrupted;
static void stop(int signal_number) { interrupted = signal_number; }
static int number(const char *text, unsigned maximum, unsigned *result)
{
    unsigned value = 0;
    if (!*text) return 0;
    for (; *text; ++text) {
        if (*text < '0' || *text > '9') return 0;
        unsigned digit = (unsigned)(*text - '0');
        if (value > maximum / 10 || (value == maximum / 10 && digit > maximum % 10)) return 0;
        value = value * 10 + digit;
    }
    *result = value;
    return 1;
}

static int usage(void)
{
    fputs("usage: tab5-gpio list | read PIN | hold PIN VALUE --seconds 1..3600\n", stderr);
    return 2;
}

int main(int argc, char **argv)
{
    if (argc == 2 && !strcmp(argv[1], "list")) {
        puts("allowed SoC GPIO: 2 3 4 5 16 18 45 47 48 51");
        puts("GPIO19 rejected: unresolved USB conflict. All other pins denied.");
        puts("Kernel GPIO cdev v2 and audited bank-label/pinmux patch required.");
        puts("Output is owned only while line fd remains open; release state is unspecified.");
        puts("Pulls and interrupts are not provided. Physical operation is unverified.");
        return 0;
    }
    unsigned pin = 0, value = 0, seconds = 0;
    int output;
    if (argc == 3 && !strcmp(argv[1], "read")) {
        output = 0;
        if (!number(argv[2], 56, &pin)) return usage();
    } else if (argc == 6 && !strcmp(argv[1], "hold") && !strcmp(argv[4], "--seconds")) {
        output = 1;
        if (!number(argv[2], 56, &pin) || !number(argv[3], 1, &value) ||
            !number(argv[5], 3600, &seconds) || !seconds) return usage();
    } else return usage();
    if (!tab5_gpio_pin_allowed(pin)) {
        fputs("pin denied by Tab5 GPIO policy\n", stderr);
        return 2;
    }
    struct sigaction action;
    memset(&action, 0, sizeof(action));
    action.sa_handler = stop;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGINT, &action, NULL) || sigaction(SIGTERM, &action, NULL)) {
        perror("signal setup"); return 1;
    }
    struct tab5_gpio line = TAB5_GPIO_INITIALIZER;
    if (tab5_gpio_open(&line, pin, output, (int)value)) { perror("GPIO request"); return 1; }
    int failed = 0;
    if (output) {
        for (unsigned elapsed = 0; elapsed < seconds && !interrupted; ++elapsed) {
            struct timespec remaining = {1, 0};
            while (!interrupted && nanosleep(&remaining, &remaining)) {
                if (errno != EINTR) { perror("hold wait"); failed = 1; break; }
            }
            if (failed) break;
        }
    } else {
        int sampled = tab5_gpio_get(&line);
        if (sampled < 0) { perror("GPIO get"); failed = 1; }
        else printf("gpio%u=%d\n", pin, sampled);
    }
    if (tab5_gpio_close(&line)) { perror("GPIO release"); failed = 1; }
    if (interrupted) return 128 + interrupted;
    return failed ? 1 : 0;
}
