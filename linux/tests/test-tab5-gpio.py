#!/usr/bin/env python3
"""Host-only GPIO ioctl fixture; no GPIO hardware or target build implied."""
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE = ROOT / "linux/buildroot-external/package/tab5-tools/src/tab5-gpio.c"


class GPIOTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        directory = pathlib.Path(cls.temp.name)
        fixture = directory / "fixture.c"
        fixture.write_text(
            '#define ioctl fixture_ioctl\n#include "' + SOURCE.as_posix() + '"\n'
            + r'''
#include <stdarg.h>
int fixture_ioctl(int fd, unsigned long op, ...)
{
    va_list ap;
    void *arg;
    va_start(ap, op); arg = va_arg(ap, void *); va_end(ap);
    if (getenv("MOCK_BUSY") && op == GPIO_V2_GET_LINE_IOCTL) {
        errno = EBUSY; return -1;
    }
    if (op == GPIO_GET_CHIPINFO_IOCTL) {
        struct gpiochip_info *c = arg;
        strcpy(c->name, "fixture"); strcpy(c->label, "host-only"); c->lines = 32;
    } else if (op == GPIO_V2_GET_LINE_IOCTL) {
        struct gpio_v2_line_request *r = arg;
        if (r->num_lines != 1 || r->offsets[0] != 16) abort();
        if (r->config.flags == GPIO_V2_LINE_FLAG_OUTPUT) {
            if (r->config.num_attrs != 1 || r->config.attrs[0].mask != 1 ||
                r->config.attrs[0].attr.id != GPIO_V2_LINE_ATTR_ID_OUTPUT_VALUES ||
                r->config.attrs[0].attr.values != 1) abort();
            /* Pending signal tests the interval before the wait loop. */
            raise(SIGTERM);
        } else if (r->config.flags != GPIO_V2_LINE_FLAG_INPUT) abort();
        r->fd = dup(fd);
    } else if (op == GPIO_V2_LINE_GET_VALUES_IOCTL) {
        struct gpio_v2_line_values *v = arg;
        if (v->mask != 1) abort();
        v->bits = 1;
    } else abort();
    return 0;
}
''', encoding="utf-8")
        cls.binary = str(directory / "gpio")
        subprocess.run(["gcc", "-Wall", "-Wextra", "-Werror", str(fixture),
                        "-o", cls.binary], check=True)
        subprocess.run(["gcc", "-Wall", "-Wextra", "-Werror", "-c", str(SOURCE),
                        "-o", str(directory / "gpio.o")], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_gpio(self, *args, env=None):
        return subprocess.run([self.binary, *args], capture_output=True,
                              text=True, timeout=3, env=env)

    def test_info(self):
        result = self.run_gpio("info", "/dev/null")
        self.assertEqual(result.returncode, 0)
        self.assertIn("lines=32", result.stdout)

    def test_input(self):
        result = self.run_gpio("get", "/dev/null", "16")
        self.assertEqual((result.returncode, result.stdout), (0, "1\n"))

    def test_output_initial_value_and_pending_termination(self):
        result = self.run_gpio("hold", "/dev/null", "16", "1")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Holding", result.stderr)

    def test_invalid_arguments(self):
        for offset in ("-1", "", "32", "4294967296", "abc", "16x"):
            with self.subTest(offset=offset):
                self.assertEqual(self.run_gpio("get", "/dev/null", offset).returncode, 2)
        self.assertEqual(self.run_gpio("hold", "/dev/null", "16", "2").returncode, 2)
        self.assertEqual(self.run_gpio("get", "/dev/null").returncode, 2)

    def test_busy_is_not_overridden(self):
        import os
        result = self.run_gpio("get", "/dev/null", "16",
                               env=dict(os.environ, MOCK_BUSY="1"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("busy", result.stderr.lower())

    def test_missing_chip(self):
        self.assertEqual(self.run_gpio("info", "/does-not-exist").returncode, 1)


if __name__ == "__main__":
    unittest.main()
