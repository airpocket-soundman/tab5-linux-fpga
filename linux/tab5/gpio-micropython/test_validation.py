"""Native module argument tests; deliberately no valid pin is opened."""
from tab5gpio import Pin


def rejects(types, function, *args, **kwargs):
    try:
        function(*args, **kwargs)
    except types:
        return
    raise AssertionError("expected argument rejection")


for bad in (True, False, 16.0, "16", None, [], {}):
    rejects(TypeError, Pin, bad)
for bad in (-1, 1 << 100):
    rejects((ValueError, OverflowError), Pin, bad)
for bad in (True, False, 1.0, "1", None):
    rejects(TypeError, Pin, 16, bad)
    rejects(TypeError, Pin, 16, Pin.OUT, value=bad)
for bad in (-1, 2, 999):
    rejects(ValueError, Pin, 16, bad)
    rejects(ValueError, Pin, 16, Pin.OUT, value=bad)
rejects(ValueError, Pin, 16, Pin.IN, value=1)
rejects(TypeError, Pin, 16, Pin.OUT, 1)
rejects(TypeError, Pin, 16, pull=1)
rejects(TypeError, Pin)
rejects(TypeError, Pin, 16, Pin.IN, mode=Pin.OUT)
for reserved in (0, 1, 6, 10, 11, 31, 32, 39, 42, 43, 44, 54, 999):
    rejects(OSError, Pin, reserved)
for method in (Pin.value, Pin.on, Pin.off, Pin.deinit, Pin.__enter__, Pin.__del__):
    rejects(TypeError, method, None)
print("PASS: native tab5gpio validation (no GPIO open)")
