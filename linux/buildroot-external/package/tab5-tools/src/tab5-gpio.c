/* SPDX-License-Identifier: MIT */
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <linux/gpio.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

static volatile sig_atomic_t stopped;
static void stop(int sig) { (void)sig; stopped = 1; }

static int fail(const char *what)
{
	perror(what);
	return 1;
}

int main(int argc, char **argv)
{
	struct gpiochip_info chip = {0};
	struct gpio_v2_line_request req = {0};
	struct gpio_v2_line_values values = { .mask = 1 };
	struct sigaction action = {0};
	sigset_t blocked, previous;
	char *end;
	unsigned long offset;
	int fd, output;
	if (argc < 3 ||
	    (strcmp(argv[1], "info") && strcmp(argv[1], "get") && strcmp(argv[1], "hold")) ||
	    (!strcmp(argv[1], "info") && argc != 3) ||
	    (!strcmp(argv[1], "get") && argc != 4) ||
	    (!strcmp(argv[1], "hold") && (argc != 5 ||
	      (strcmp(argv[4], "0") && strcmp(argv[4], "1"))))) {
		fprintf(stderr, "Usage: tab5-gpio info CHIP\n"
			"       tab5-gpio get CHIP OFFSET\n"
			"       tab5-gpio hold CHIP OFFSET 0|1\n"
			"CHIP is /dev/gpiochipN; OFFSET is chip-relative, not a board pin.\n"
			"hold owns the line until SIGINT/SIGTERM; release state is driver-defined.\n");
		return 2;
	}
	/* Validate before opening a device, including negative/overflow input. */
	if (argc >= 4) {
		errno = 0;
		offset = strtoul(argv[3], &end, 10);
		if (errno || !*argv[3] || *end || argv[3][0] == '-' || offset > UINT_MAX) {
			fprintf(stderr, "Invalid offset\n");
			return 2;
		}
		req.offsets[0] = (unsigned int)offset;
	}
	fd = open(argv[2], O_RDONLY | O_CLOEXEC);
	if (fd < 0) return fail("open gpiochip");
	if (ioctl(fd, GPIO_GET_CHIPINFO_IOCTL, &chip) < 0) {
		close(fd); return fail("GPIO_GET_CHIPINFO_IOCTL");
	}
	if (argc == 3) {
		printf("%s label=%s lines=%u\n", chip.name, chip.label, chip.lines);
		close(fd); return 0;
	}
	if (req.offsets[0] >= chip.lines) {
		fprintf(stderr, "Offset outside this chip\n"); close(fd); return 2;
	}
	output = !strcmp(argv[1], "hold");
	req.num_lines = 1;
	strcpy(req.consumer, "tab5-gpio");
	req.config.flags = output ? GPIO_V2_LINE_FLAG_OUTPUT : GPIO_V2_LINE_FLAG_INPUT;
	if (output) {
		/* Set the initial level atomically with requesting the output. */
		req.config.num_attrs = 1;
		req.config.attrs[0].mask = 1;
		req.config.attrs[0].attr.id = GPIO_V2_LINE_ATTR_ID_OUTPUT_VALUES;
		req.config.attrs[0].attr.values = argv[4][0] == '1';
		action.sa_handler = stop;
		sigemptyset(&action.sa_mask);
		sigemptyset(&blocked);
		sigaddset(&blocked, SIGINT); sigaddset(&blocked, SIGTERM);
		if (sigaction(SIGINT, &action, NULL) || sigaction(SIGTERM, &action, NULL) ||
		    sigprocmask(SIG_BLOCK, &blocked, &previous)) {
			close(fd); return fail("signal setup");
		}
	}
	if (ioctl(fd, GPIO_V2_GET_LINE_IOCTL, &req) < 0) {
		close(fd); return fail("GPIO_V2_GET_LINE_IOCTL (busy/unsupported/permission?)");
	}
	close(fd);
	if (output) {
		fprintf(stderr, "Holding offset %u at %s; interrupt to release\n", req.offsets[0], argv[4]);
		while (!stopped) sigsuspend(&previous);
	} else if (ioctl(req.fd, GPIO_V2_LINE_GET_VALUES_IOCTL, &values) < 0) {
		close(req.fd); return fail("GPIO_V2_LINE_GET_VALUES_IOCTL");
	} else {
		printf("%u\n", (unsigned int)(values.bits & 1));
	}
	close(req.fd);
	return 0;
}
