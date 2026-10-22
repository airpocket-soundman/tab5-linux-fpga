# Tab5 console touch gestures

`tab5-touch-scroll.c` is a single-process, static NOMMU evdev consumer.
It finds `Tab5 ST712x Touchscreen`, consumes complete SYN_REPORT frames,
and sends the existing aligned TIOCLINUX/SCROLLCONSOLE ABI to tty1.
No shell commands, terminal characters, or input grabs are involved.
It ignores gestures while another VT is foreground. Lost event frames
cancel the current gesture. Unplug/reprobe is retried.

Arguments: `tab5-touch-scroll [x|y] [1|-1] [pixels-per-line]`.
The startup service uses `x 1 32` for the current `fbcon=rotate:1` display.
Axis and direction need physical swipe verification; they are not inferred
from a compiled driver. Dragging content down reveals older output.
`tab5-touch-scroll --lines -5` requests five older rows without touch for
diagnostics; `--lines 128` returns to the live view.

Kernel patches 0081 (touch input) and 0082 (bounded tty1 history) are both
required. The history holds 128 complete scrolled-off glyph rows with a
160-column maximum, using 40 KiB of static RAM. Only full-screen upward
scrolls are captured. Partial editor scrolling is not captured. This is
glyph/attribute display history, not Unicode selection or a PTY log.
New output returns to the live view; CSI 3 J clears history. The live screen
and shell cursor are never replaced with history data. Other VTs retain
their existing implementation. Full-screen applications can still enter
history if they perform full-screen scrolling.

The standalone terminal-app build compiles this helper with the same
RV32IMAC/uClibc bFLT toolchain. It is always installed in internal rootfs,
including the optional SD application-storage build. S98 starts it and
retries discovery until touch input is available.

Acceptance on hardware: touch probe and event stream, both swipe directions,
history saturation, return to live on typed/output text, CSI 3 J, resize,
and regression checks for Wi-Fi, microSD, clear, vi and Vim. A successful
compile alone does not establish any of these runtime results.
