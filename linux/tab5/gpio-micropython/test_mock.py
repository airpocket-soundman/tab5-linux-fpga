"""Run ONLY with an interpreter compiled TAB5_GPIO_TEST_BACKEND=1."""
import gc
import tab5gpio
from tab5gpio import Pin

assert hasattr(tab5gpio, "_test_stats"), "requires compile-time host test backend"
stats = tab5gpio._test_stats


def rejects(types, function, *args, **kwargs):
    try:
        function(*args, **kwargs)
    except types:
        return
    raise AssertionError("expected rejection")


assert stats() == (0, 0, 0, 0)
# Import runs the invalid argument cases: no board/chip/line calls are allowed.
import test_validation
assert stats() == (0, 0, 0, 0)

p = Pin(16, Pin.OUT, value=1)
assert stats()[3] == 1 and p.value() == 1
p.off()
assert p.value() == 0
p.on()
assert p.value() == 1
p.value(0)
assert p.value() == 0
for bad in (True, False, 1.0, "1", None):
    rejects(TypeError, p.value, bad)
for bad in (-1, 2):
    rejects(ValueError, p.value, bad)
rejects(OSError, Pin, 16, Pin.OUT)
assert stats()[3] == 1
p.deinit()
before = stats()
p.deinit()
p.__del__()
assert stats() == before
for function in (p.value, p.on, p.off, p.__enter__):
    rejects(OSError, function)

with Pin(16, Pin.IN) as p:
    assert p.value() == 0
    rejects(OSError, p.on)
    rejects(OSError, p.off)
    rejects(OSError, p.value, 1)
assert stats()[3] == 0
try:
    with Pin(16, Pin.OUT) as p:
        raise ValueError("propagate")
except ValueError:
    pass
else:
    raise AssertionError("with swallowed exception")
assert stats()[3] == 0

# No GC registration race, and close failure cannot cause stale fd reuse closes.
old = Pin(16, Pin.OUT)
tab5gpio._test_fail_close()
rejects(OSError, old.deinit)
assert stats()[3] == 0
replacement = Pin(16, Pin.OUT, value=1)
before = stats()
old.deinit()
old.__del__()
del old
gc.collect()
assert stats() == before and replacement.value() == 1
replacement.deinit()
del replacement, p
gc.collect()


def abandoned():
    pin = Pin(16, Pin.OUT)
    assert pin.value() == 0


before = stats()
abandoned()
gc.collect()
gc.collect()
assert stats()[3] == 0 and stats()[2] == before[2] + 1

# Finalization suppresses close errors and still releases model ownership.
abandoned()
tab5gpio._test_fail_close()
gc.collect()
gc.collect()
assert stats()[3] == 0

for pin in (2, 3, 4, 5, 16, 18, 45, 47, 48, 51):
    with Pin(pin, Pin.OUT, value=pin % 2) as p:
        assert p.value() == pin % 2
assert stats()[3] == 0
print("PASS: native tab5gpio mock I/O, exclusivity, context, GC and descriptor reuse")
