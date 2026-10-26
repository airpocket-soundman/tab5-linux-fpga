/* SPDX-License-Identifier: MIT */
#ifndef TAB5_BMP_H
#define TAB5_BMP_H
#include <stdint.h>
#include <stdio.h>

/* Bounded row-at-a-time decoding: no width*height allocation. */
struct bmp {
	FILE *file;
	uint32_t width, height, stride, offset;
	unsigned bits, topdown, rgb565;
};
int bmp_open(struct bmp *b, const char *path);
int bmp_row(struct bmp *b, uint32_t y, unsigned char *rgb);
void bmp_close(struct bmp *b);
int bmp_save_yuyv(const char *path, const unsigned char *data, size_t size,
		 unsigned width, unsigned height, unsigned stride);
#endif
