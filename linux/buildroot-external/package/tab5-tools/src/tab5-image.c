/* SPDX-License-Identifier: MIT */
#include "bmp.h"
#include <errno.h>
#include <fcntl.h>
#include <linux/fb.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

static uint32_t component(unsigned v, struct fb_bitfield f)
{ return f.length ? ((v*((1u<<f.length)-1)+127)/255)<<f.offset : 0; }
static int field_valid(struct fb_bitfield f, unsigned bits)
{ return f.length<=8 && f.offset<=bits && f.length<=bits-f.offset && !f.msb_right; }

int main(int argc, char **argv)
{
	struct bmp b;
	struct fb_var_screeninfo v;
	struct fb_fix_screeninfo f;
	unsigned char rgb[5760], pixels[7680];
	int fd=-1, status=1, info;
	uint32_t checksum=2166136261u;
	if (argc<2 || argc>3 || (argc==3 && strcmp(argv[1], "--info") && strncmp(argv[2], "/dev/", 5))) {
		fprintf(stderr, "Usage: tab5-image --info FILE.bmp\n       tab5-image FILE.bmp [/dev/fb0]\n"); return 2;
	}
	info=!strcmp(argv[1], "--info");
	if (info && argc!=3) return 2;
	if (bmp_open(&b, argv[info ? 2 : 1])) { perror("BMP"); return 1; }
	if (!info) {
		fd=open(argc==3 ? argv[2] : "/dev/fb0", O_RDWR|O_CLOEXEC);
		if (fd<0 || ioctl(fd, FBIOGET_VSCREENINFO, &v) || ioctl(fd, FBIOGET_FSCREENINFO, &f)) goto error;
		if (f.type!=FB_TYPE_PACKED_PIXELS || f.visual!=FB_VISUAL_TRUECOLOR || v.nonstd || v.grayscale ||
		    (v.bits_per_pixel!=16 && v.bits_per_pixel!=24 && v.bits_per_pixel!=32) ||
		    !v.red.length || !v.green.length || !v.blue.length ||
		    !field_valid(v.red,v.bits_per_pixel) || !field_valid(v.green,v.bits_per_pixel) ||
		    !field_valid(v.blue,v.bits_per_pixel) || !field_valid(v.transp,v.bits_per_pixel) ||
		    !v.xres || !v.yres || (uint64_t)v.xoffset+v.xres>v.xres_virtual ||
		    (uint64_t)v.yoffset+v.yres>v.yres_virtual ||
		    ((uint64_t)v.xoffset+v.xres)*(v.bits_per_pixel/8)>f.line_length ||
		    ((uint64_t)v.yoffset+v.yres)*f.line_length>f.smem_len) {
			errno=ENOTSUP; goto error;
		}
	}
	for (uint32_t y=0; y<b.height; y++) {
		unsigned bytes=info ? 0 : v.bits_per_pixel/8;
		if (bmp_row(&b, y, rgb)) goto error;
		for (uint32_t x=0; x<b.width*3; x++) checksum=(checksum^rgb[x])*16777619u;
		if (info || y>=v.yres) continue;
		unsigned width=b.width<v.xres ? b.width : v.xres;
		for (unsigned x=0; x<width; x++) {
			uint32_t p=component(rgb[3*x],v.red)|component(rgb[3*x+1],v.green)|
				component(rgb[3*x+2],v.blue)|component(255,v.transp);
			for (unsigned i=0; i<bytes; i++) pixels[x*bytes+i]=p>>(i*8);
		}
		/* pwrite avoids mapping an entire framebuffer on NOMMU. */
		size_t length=width*bytes, done=0;
		off_t offset=(off_t)((uint64_t)(y+v.yoffset)*f.line_length+(uint64_t)v.xoffset*bytes);
		while (done<length) {
			ssize_t n=pwrite(fd,pixels+done,length-done,offset+(off_t)done);
			if (n<0 && errno==EINTR) continue;
			if (n<=0) { if (!n) errno=EIO; goto error; }
			done+=(size_t)n;
		}
	}
	printf("%ux%u BMP%u RGB24-FNV1a=%08x%s\n",b.width,b.height,b.bits,checksum,
		info ? "" : " (top-left, clipped to framebuffer; no rotation)");
	status=0;
	goto out;
error:
	perror("image");
out:
	if (fd>=0) close(fd);
	bmp_close(&b);
	return status;
}
