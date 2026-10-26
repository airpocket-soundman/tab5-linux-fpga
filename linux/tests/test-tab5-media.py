#!/usr/bin/env python3
"""Real BMP codec plus simulated V4L2/fbdev integration; no device access."""
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

SRC = Path(__file__).resolve().parents[1] / "buildroot-external/package/tab5-tools/src"

CAMERA_FIXTURE = r'''
#define ioctl mock_ioctl
#define mmap mock_mmap
#define munmap mock_munmap
#define poll mock_poll
#define clock_gettime mock_clock
#include "tab5-camera.c"
#include <assert.h>
#include <stdarg.h>
static int active, live, allocated_buffers, attempts, ticks;
static const char *scenario(void) { const char *s=getenv("MOCK"); return s ? s : "ok"; }
static int is(const char *s) { return !strcmp(scenario(),s); }
int mock_ioctl(int fd, unsigned long command, ...)
{
    va_list args; void *arg; (void)fd;
    va_start(args,command); arg=va_arg(args,void *); va_end(args);
    switch(command) {
    case VIDIOC_QUERYCAP: {
        struct v4l2_capability *c=arg;
        c->capabilities=V4L2_CAP_DEVICE_CAPS;
        c->device_caps=V4L2_CAP_VIDEO_CAPTURE|V4L2_CAP_STREAMING;
        if (is("no-streaming")) c->device_caps=V4L2_CAP_VIDEO_CAPTURE;
        break;
    }
    case VIDIOC_ENUM_FMT: {
        struct v4l2_fmtdesc *d=arg;
        if (d->index) { errno=EINVAL; return -1; }
        d->pixelformat=V4L2_PIX_FMT_YUYV; break;
    }
    case VIDIOC_S_FMT: {
        struct v4l2_format *f=arg;
        f->fmt.pix.width=2; f->fmt.pix.height=2;
        f->fmt.pix.bytesperline=8; f->fmt.pix.sizeimage=16;
        if (is("wrong-format")) f->fmt.pix.pixelformat=V4L2_PIX_FMT_MJPEG;
        if (is("huge-stride")) f->fmt.pix.bytesperline=0xffffffffu;
        break;
    }
    case VIDIOC_REQBUFS: {
        struct v4l2_requestbuffers *r=arg;
        if (!r->count) { allocated_buffers=0; break; }
        allocated_buffers=1;
        if (is("zero-buffers")) r->count=0;
        break;
    }
    case VIDIOC_QUERYBUF: {
        struct v4l2_buffer *b=arg; b->length=16; b->m.offset=b->index*4096;
        if (is("large-buffer")) b->length=MAX_FRAME+1;
        break;
    }
    case VIDIOC_QBUF: break;
    case VIDIOC_STREAMON: active=1; break;
    case VIDIOC_STREAMOFF: active=0; break;
    case VIDIOC_DQBUF: {
        struct v4l2_buffer *b=arg;
        if (is("eagain") && !attempts++) { errno=EAGAIN; return -1; }
        b->index=is("bad-index") ? 2 : 0;
        b->bytesused=is("short-frame") ? 2 : is("overrun") ? 17 : 16;
        if (is("bad-frame") && !attempts++) b->flags=V4L2_BUF_FLAG_ERROR;
        break;
    }
    default: abort();
    }
    return 0;
}
void *mock_mmap(void *addr,size_t size,int prot,int flags,int fd,off_t offset)
{
    unsigned char *p;
    (void)addr; (void)prot; (void)flags; (void)fd; (void)offset;
    if (is("mmap-failure")) { errno=ENOMEM; return MAP_FAILED; }
    p=calloc(1,size); assert(p); live++;
    /* Stride padding is deliberately not pixel data. */
    p[0]=16; p[1]=128; p[2]=235; p[3]=128;
    p[8]=81; p[9]=90; p[10]=81; p[11]=240;
    return p;
}
int mock_munmap(void *p,size_t size) { (void)size; live--; free(p); return 0; }
int mock_poll(struct pollfd *p,nfds_t count,int timeout)
{
    (void)count; assert(timeout>0 && timeout<=10000);
    if (is("timeout")) return 0;
    if (is("interrupt")) { raise(SIGINT); errno=EINTR; return -1; }
    p->revents=is("disconnect") ? POLLHUP : POLLIN; return 1;
}
int mock_clock(clockid_t id,struct timespec *t)
{ (void)id; t->tv_sec=ticks++; t->tv_nsec=0; return 0; }
__attribute__((destructor)) static void verify_cleanup(void)
{ assert(!active && !live && !allocated_buffers); }
'''

FB_FIXTURE = r'''
#define ioctl mock_ioctl
#define pwrite mock_pwrite
#include "tab5-image.c"
#undef pwrite
#include <stdarg.h>
int mock_ioctl(int fd,unsigned long command,...)
{
    va_list args; void *arg; (void)fd;
    va_start(args,command); arg=va_arg(args,void *); va_end(args);
    if (command==FBIOGET_VSCREENINFO) {
        struct fb_var_screeninfo *v=arg;
        memset(v,0,sizeof(*v));
        v->xres=2; v->yres=2; v->xres_virtual=4; v->yres_virtual=4;
        v->xoffset=1; v->yoffset=1; v->bits_per_pixel=16;
        v->red.offset=11; v->red.length=5;
        v->green.offset=5; v->green.length=6; v->blue.length=5;
        if (getenv("BAD_FB")) v->xoffset=4;
    } else if (command==FBIOGET_FSCREENINFO) {
        struct fb_fix_screeninfo *f=arg;
        memset(f,0,sizeof(*f)); f->type=FB_TYPE_PACKED_PIXELS;
        f->visual=FB_VISUAL_TRUECOLOR; f->line_length=12; f->smem_len=48;
    } else abort();
    return 0;
}
ssize_t mock_pwrite(int fd,const void *data,size_t length,off_t offset)
{
    int out=open(getenv("FB_OUTPUT"),O_WRONLY|O_CREAT,0600);
    ssize_t n; (void)fd;
    if (out<0) return -1;
    if (lseek(out,offset,SEEK_SET)<0) { close(out); return -1; }
    n=write(out,data,length); close(out); return n;
}
'''


def bmp24(width=2, height=2, topdown=False):
    rows = [bytes((0, 0, 255, 0, 255, 0, 0, 0)),
            bytes((255, 0, 0, 255, 255, 255, 0, 0))]
    data = b"".join(rows if topdown else reversed(rows))
    header = struct.pack("<2sIHHI", b"BM", 54+len(data), 0, 0, 54)
    return header + struct.pack("<IiiHHIIiiII", 40, width, -height if topdown else height,
                                1, 24, 0, len(data), 0, 0, 0, 0) + data


class MediaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.work = Path(cls.temp.name)
        for name, fixture, source in (("image", None, "tab5-image.c"),
                                       ("camera", CAMERA_FIXTURE, "tab5-camera.c"),
                                       ("fb", FB_FIXTURE, "tab5-image.c")):
            input_file = SRC / source
            if fixture:
                input_file = cls.work / (name+".c")
                input_file.write_text(fixture)
            subprocess.run(["gcc", "-Wall", "-Wextra", "-Werror", "-I", str(SRC),
                            str(input_file), str(SRC/"bmp.c"), "-o", str(cls.work/name)], check=True)
        subprocess.run(["gcc", "-Wall", "-Wextra", "-Werror", "-c", str(SRC/"tab5-camera.c"),
                        "-o", str(cls.work/"camera.o")], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.case = tempfile.TemporaryDirectory(dir=self.work)
        self.addCleanup(self.case.cleanup)
        self.directory = Path(self.case.name)

    def run_tool(self, name, *args, **env):
        return subprocess.run([str(self.work/name), *map(str, args)],
                              env=dict(os.environ, **env), capture_output=True, text=True, timeout=3)

    def test_bmp_orientation_checksum(self):
        results = []
        for topdown in (False, True):
            path = self.directory / str(topdown)
            path.write_bytes(bmp24(topdown=topdown))
            result = self.run_tool("image", "--info", path)
            self.assertEqual(result.returncode, 0, result.stderr)
            results.append(result.stdout)
        self.assertEqual(results[0], results[1])
        checksum = 2166136261
        for pixel in bytes((255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 255)):
            checksum = ((checksum ^ pixel) * 16777619) & 0xffffffff
        self.assertIn(f"{checksum:08x}", results[0])

    def test_bmp_malformed(self):
        cases = [b"", bmp24()[:53], bmp24()[:-1]]
        for offset, value in ((18, 1921), (22, 0), (10, 20), (30, 1), (10, 0xfffffff0)):
            data = bytearray(bmp24()); struct.pack_into("<I", data, offset, value); cases.append(data)
        for i, data in enumerate(cases):
            path = self.directory / str(i); path.write_bytes(data)
            self.assertEqual(self.run_tool("image", "--info", path).returncode, 1)

    def test_rgb565_and_rgb555(self):
        for compression, masks, red in ((3, (0xf800, 0x7e0, 31), 0xf800), (0, (), 0x7c00)):
            header = bytearray(bmp24())[:54]
            struct.pack_into("<H", header, 28, 16)
            struct.pack_into("<I", header, 30, compression)
            struct.pack_into("<I", header, 10, 54+4*len(masks))
            path = self.directory / str(compression)
            path.write_bytes(header + b"".join(struct.pack("<I", m) for m in masks)
                             + struct.pack("<4H", red, red, red, red))
            result = self.run_tool("image", "--info", path)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_framebuffer_stride_offset_and_color(self):
        image = self.directory/"image.bmp"; image.write_bytes(bmp24())
        output = self.directory/"fb"
        result = self.run_tool("fb", image, "/dev/null", FB_OUTPUT=str(output))
        self.assertEqual(result.returncode, 0, result.stderr)
        data = output.read_bytes()
        self.assertEqual(data[:14], bytes(14))
        self.assertEqual(data[14:18], struct.pack("<HH", 0xf800, 0x7e0))
        self.assertEqual(data[26:30], struct.pack("<HH", 0x1f, 0xffff))

    def test_invalid_framebuffer_does_not_write(self):
        image = self.directory/"image.bmp"; image.write_bytes(bmp24())
        output = self.directory/"fb"
        self.assertEqual(self.run_tool("fb", image, "/dev/null", FB_OUTPUT=str(output), BAD_FB="1").returncode, 1)
        self.assertFalse(output.exists())

    def test_camera_capture_and_no_overwrite(self):
        output = self.directory/"capture.bmp"
        result = self.run_tool("camera", "capture", "/dev/null", output)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = output.read_bytes()
        self.assertEqual(len(data), 70)
        self.assertEqual(data[54:60], bytes((0, 0, 255, 0, 0, 255)))
        self.assertEqual(data[62:68], bytes((0, 0, 0, 255, 255, 255)))
        self.assertEqual(self.run_tool("camera", "capture", "/dev/null", output).returncode, 1)
        self.assertEqual(output.read_bytes(), data)
        self.assertEqual(self.run_tool("image", "--info", output).returncode, 0)

    def test_camera_cleanup_failures(self):
        for scenario in ("timeout", "interrupt", "disconnect", "bad-index", "overrun", "short-frame",
                         "wrong-format", "huge-stride", "zero-buffers", "large-buffer", "mmap-failure", "no-streaming"):
            with self.subTest(scenario=scenario):
                output = self.directory/scenario
                result = self.run_tool("camera", "capture", "/dev/null", output, MOCK=scenario)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertFalse(output.exists())

    def test_camera_retries_invalid_frame_and_eagain(self):
        for scenario in ("eagain", "bad-frame"):
            result = self.run_tool("camera", "capture", "/dev/null", self.directory/scenario, MOCK=scenario)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_camera_info_and_bad_arguments(self):
        self.assertIn("YUYV", self.run_tool("camera", "--info", "/dev/null").stdout)
        for dimensions in (("641", "480"), ("3", "2"), ("2", "0"), ("-2", "2")):
            self.assertEqual(self.run_tool("camera", "capture", "/dev/null", "unused", *dimensions).returncode, 2)


if __name__ == "__main__":
    unittest.main()
