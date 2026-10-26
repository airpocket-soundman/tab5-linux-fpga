#!/usr/bin/env python3
"""Run the native Pin binding in a real host-built MicroPython with fake GPIO.

Usage: python3 test-tab5-micropython.py /path/to/host/micropython
The interpreter must include tab5io and gc; no target hardware is accessed.
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

PRELOAD = r'''
#define _GNU_SOURCE
#include <assert.h>
#include <dlfcn.h>
#include <errno.h>
#include <linux/gpio.h>
#include <stdarg.h>
#include <stdlib.h>
#include <unistd.h>
static int pins[1024], levels[1024], directions[1024], count;
int ioctl(int fd,unsigned long command,...)
{
    va_list args; void *arg;
    va_start(args,command); arg=va_arg(args,void *); va_end(args);
    assert(fd>=0 && fd<1024);
    switch(command) {
    case GPIO_GET_CHIPINFO_IOCTL: ((struct gpiochip_info *)arg)->lines=32; return 0;
    case GPIO_V2_GET_LINE_IOCTL: {
        struct gpio_v2_line_request *r=arg;
        for (int i=0;i<1024;i++) if (pins[i] && pins[i]==(int)r->offsets[0]+1) { errno=EBUSY; return -1; }
        assert(r->num_lines==1);
        int n=dup(fd); assert(n>=0 && n<1024);
        pins[n]=r->offsets[0]+1; count++;
        directions[n]=r->config.flags==GPIO_V2_LINE_FLAG_OUTPUT;
        if (directions[n]) {
            assert(r->config.num_attrs==1 && r->config.attrs[0].mask==1);
            assert(r->config.attrs[0].attr.id==GPIO_V2_LINE_ATTR_ID_OUTPUT_VALUES);
            levels[n]=r->config.attrs[0].attr.values;
        } else levels[n]=1;
        r->fd=n; return 0;
    }
    case GPIO_V2_LINE_GET_VALUES_IOCTL: {
        struct gpio_v2_line_values *v=arg;
        assert(pins[fd] && v->mask==1); v->bits=levels[fd]; return 0;
    }
    case GPIO_V2_LINE_SET_VALUES_IOCTL: {
        struct gpio_v2_line_values *v=arg;
        assert(pins[fd] && directions[fd] && v->mask==1);
        levels[fd]=v->bits; return 0;
    }
    default: errno=ENOTTY; return -1;
    }
}
int close(int fd)
{
    static int (*real_close)(int);
    if (!real_close) real_close=dlsym(RTLD_NEXT,"close");
    if (fd>=0 && fd<1024 && pins[fd]) { pins[fd]=0; count--; }
    return real_close(fd);
}
__attribute__((destructor)) static void check_cleanup(void) { assert(count==0); }
'''

SCRIPT = r'''
from tab5io import Pin
import gc

def raises(exception, fn):
    try:
        fn()
    except exception:
        return
    raise AssertionError('expected exception')

p=Pin('/dev/null',16,Pin.IN)
assert p.value()==1
raises(ValueError,lambda:p.value(1))
raises(OSError,lambda:Pin('/dev/null',16))
p.deinit()
p.deinit()
raises(ValueError,p.value)
with Pin('/dev/null',16,Pin.OUT,value=1) as p:
    assert p.value()==1
    p.off()
    assert p.value()==0
    p.on()
    assert p.value()==1
    raises(ValueError,lambda:p.value(2))
raises(ValueError,p.value)

try:
    with Pin('/dev/null',16) as p:
        raise RuntimeError('cleanup on exception')
except RuntimeError:
    pass
raises(ValueError,p.value)

with Pin('/dev/null',16,Pin.OUT) as p:
    class ReleaseDuringConversion:
        def __int__(self):
            p.deinit()
            return 1
    raises(ValueError,lambda:p.value(ReleaseDuringConversion()))

for args in (('/dev/null',-1),('/dev/null',32),('/dev/null',16,7)):
    raises(ValueError,lambda:Pin(*args))
raises(OSError,lambda:Pin('/no-such-chip',16))
raises(ValueError,lambda:Pin('/dev/null',16,Pin.OUT,value=2))

def abandoned():
    Pin('/dev/null',16,Pin.IN)
abandoned()
gc.collect()
with Pin('/dev/null',16) as p:
    assert p.value()==1

for i in range(100):
    with Pin('/dev/null',16,Pin.OUT,value=i%2) as p:
        assert p.value()==i%2
gc.collect()
print('tab5io: input/output, ownership, lifecycle, exceptions and GC PASS')
'''


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    binary = str(Path(sys.argv[1]).resolve())
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        (root/"mock.c").write_text(PRELOAD)
        (root/"test.py").write_text(SCRIPT)
        library = root/"mock.so"
        subprocess.run(["gcc", "-shared", "-fPIC", "-Wall", "-Wextra", "-Werror",
                        str(root/"mock.c"), "-ldl", "-o", str(library)], check=True)
        subprocess.run([binary, str(root/"test.py")],
                       env=dict(os.environ, LD_PRELOAD=str(library)), check=True, timeout=10)


if __name__ == "__main__":
    main()
