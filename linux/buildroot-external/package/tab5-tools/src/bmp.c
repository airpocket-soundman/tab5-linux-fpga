/* SPDX-License-Identifier: MIT */
#include "bmp.h"
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static uint32_t le32(const unsigned char *p)
{ return (uint32_t)p[0] | (uint32_t)p[1]<<8 | (uint32_t)p[2]<<16 | (uint32_t)p[3]<<24; }
static unsigned le16(const unsigned char *p) { return p[0] | (unsigned)p[1]<<8; }
static void put32(unsigned char *p, uint32_t n)
{ p[0]=n; p[1]=n>>8; p[2]=n>>16; p[3]=n>>24; }
static int bad(struct bmp *b)
{ bmp_close(b); errno = EINVAL; return -1; }

void bmp_close(struct bmp *b)
{ if (b->file) fclose(b->file); b->file = NULL; }

int bmp_open(struct bmp *b, const char *path)
{
	unsigned char h[54], masks[12];
	uint32_t dib, compression, height;
	struct stat st;
	memset(b, 0, sizeof(*b));
	b->file = fopen(path, "rb");
	if (!b->file) return -1;
	if (fstat(fileno(b->file), &st) || fread(h, 1, sizeof(h), b->file) != sizeof(h)) return bad(b);
	dib = le32(h+14); height = le32(h+22); compression = le32(h+30);
	b->width = le32(h+18); b->bits = le16(h+28); b->offset = le32(h+10);
	b->topdown = !!(height & 0x80000000u);
	b->height = b->topdown ? 0u-height : height;
	if (h[0]!='B' || h[1]!='M' || dib<40 || dib>124 || le16(h+26)!=1 ||
	    !b->width || b->width>1920 || !b->height || b->height>1080 ||
	    b->offset<14+dib || (b->bits!=16 && b->bits!=24) ||
	    (compression!=0 && !(compression==3 && b->bits==16))) return bad(b);
	if (compression==3) {
		/* Masks follow BITMAPINFOHEADER, or occupy its extended fields. */
		if (b->offset<66 || (dib!=40 && dib<52) ||
		    fread(masks, 1, sizeof(masks), b->file)!=sizeof(masks)) return bad(b);
		if (le32(masks)==0xf800 && le32(masks+4)==0x7e0 && le32(masks+8)==0x1f) b->rgb565=1;
		else if (le32(masks)!=0x7c00 || le32(masks+4)!=0x3e0 || le32(masks+8)!=0x1f) return bad(b);
	}
	b->stride = ((b->width*b->bits+31)/32)*4;
	if ((uint64_t)b->offset+(uint64_t)b->stride*b->height>0x7fffffffu ||
	    (uint64_t)b->offset+(uint64_t)b->stride*b->height>(uint64_t)st.st_size) return bad(b);
	return 0;
}

int bmp_row(struct bmp *b, uint32_t y, unsigned char *rgb)
{
	unsigned char row[5760];
	uint32_t line = b->topdown ? y : b->height-1-y;
	if (y>=b->height || fseek(b->file, (long)(b->offset+line*b->stride), SEEK_SET) ||
	    fread(row, 1, b->stride, b->file)!=b->stride) { errno=EIO; return -1; }
	for (uint32_t x=0; x<b->width; x++) {
		if (b->bits==24) {
			rgb[3*x]=row[3*x+2]; rgb[3*x+1]=row[3*x+1]; rgb[3*x+2]=row[3*x];
		} else {
			unsigned p=le16(row+2*x), g=(p>>5)&(b->rgb565 ? 63 : 31);
			rgb[3*x]=((p>>(b->rgb565 ? 11 : 10))&31)*255/31;
			rgb[3*x+1]=g*255/(b->rgb565 ? 63 : 31); rgb[3*x+2]=(p&31)*255/31;
		}
	}
	return 0;
}

static unsigned char clamp(int n) { return n<0 ? 0 : n>255 ? 255 : n; }

int bmp_save_yuyv(const char *path, const unsigned char *data, size_t size,
		 unsigned width, unsigned height, unsigned stride)
{
	unsigned char header[54]={0}, row[1920];
	unsigned outstride;
	int fd, saved;
	FILE *out;
	if (!width || width>640 || (width&1) || !height || height>480 ||
	    stride<width*2 || size<(size_t)(height-1)*stride+width*2) { errno=EINVAL; return -1; }
	outstride=(width*3+3)&~3u;
	header[0]='B'; header[1]='M'; put32(header+2, 54+height*outstride);
	put32(header+10, 54); put32(header+14, 40); put32(header+18, width);
	put32(header+22, height); header[26]=1; header[28]=24;
	put32(header+34, height*outstride);
	fd=open(path, O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC, 0644);
	if (fd<0) return -1;
	out=fdopen(fd, "wb");
	if (!out) { saved=errno; close(fd); unlink(path); errno=saved; return -1; }
	if (fwrite(header, 1, 54, out)!=54) goto error;
	for (unsigned y=0; y<height; y++) {
		const unsigned char *in=data+(height-1-y)*stride;
		memset(row, 0, outstride);
		for (unsigned x=0; x<width; x+=2) {
			int d=(int)in[2*x+1]-128, e=(int)in[2*x+3]-128;
			for (unsigned i=0; i<2; i++) {
				int c=(int)in[2*x+2*i]-16;
				/* Limited-range BT.601 YUYV -> BGR24. */
				row[3*(x+i)]=clamp((298*c+516*d+128)>>8);
				row[3*(x+i)+1]=clamp((298*c-100*d-208*e+128)>>8);
				row[3*(x+i)+2]=clamp((298*c+409*e+128)>>8);
			}
		}
		if (fwrite(row, 1, outstride, out)!=outstride) goto error;
	}
	if (fflush(out) || fsync(fd)) goto error;
	if (fclose(out)) { saved=errno; unlink(path); errno=saved; return -1; }
	return 0;
error:
	saved=errno ? errno : EIO; fclose(out); unlink(path); errno=saved; return -1;
}
