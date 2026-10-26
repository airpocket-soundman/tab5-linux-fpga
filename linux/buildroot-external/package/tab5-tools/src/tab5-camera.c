/* SPDX-License-Identifier: MIT */
#include "bmp.h"
#include <errno.h>
#include <fcntl.h>
#include <linux/videodev2.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define MAX_FRAME (2u*1024*1024)
static volatile sig_atomic_t stopped;
static void stop(int sig) { (void)sig; stopped=1; }
static int control(int fd, unsigned long command, void *arg)
{
	int rc;
	do { rc=ioctl(fd,command,arg); } while (rc<0 && errno==EINTR && !stopped);
	return rc;
}
static int64_t milliseconds(void)
{
	struct timespec t;
	if (clock_gettime(CLOCK_MONOTONIC,&t)) return -1;
	return (int64_t)t.tv_sec*1000+t.tv_nsec/1000000;
}
static int dimension(const char *text, unsigned limit, unsigned *value)
{
	char *end;
	unsigned long n;
	errno=0; n=strtoul(text,&end,10);
	if (!*text || *end || errno || n==0 || n>limit) return -1;
	*value=(unsigned)n; return 0;
}
int main(int argc, char **argv)
{
	struct v4l2_capability cap={0};
	struct v4l2_format format={.type=V4L2_BUF_TYPE_VIDEO_CAPTURE};
	struct v4l2_requestbuffers request={.count=2,.type=V4L2_BUF_TYPE_VIDEO_CAPTURE,.memory=V4L2_MEMORY_MMAP};
	struct { void *address; size_t length; } buffers[2]={{0}};
	enum v4l2_buf_type type=V4L2_BUF_TYPE_VIDEO_CAPTURE;
	struct sigaction action={0};
	unsigned width=160,height=120, mapped=0;
	int fd=-1,status=1,streaming=0,allocated=0,info;
	int saved=0;
	uint32_t caps;
	int64_t deadline,now;
	if (argc<3 || (strcmp(argv[1],"--info") && strcmp(argv[1],"capture")) ||
	    (!strcmp(argv[1],"--info") && argc!=3) ||
	    (!strcmp(argv[1],"capture") && argc!=4 && argc!=6)) {
		fprintf(stderr,"Usage: tab5-camera --info /dev/videoN\n"
			"       tab5-camera capture /dev/videoN NEW.bmp [WIDTH HEIGHT]\n"
			"YUYV BT.601 limited range only; default 160x120, maximum 640x480.\n"); return 2;
	}
	info=!strcmp(argv[1],"--info");
	if (argc==6 && (dimension(argv[4],640,&width) || dimension(argv[5],480,&height) || (width&1))) return 2;
	action.sa_handler=stop; sigemptyset(&action.sa_mask);
	if (sigaction(SIGINT,&action,NULL) || sigaction(SIGTERM,&action,NULL)) { perror("signal"); return 1; }
	fd=open(argv[2],O_RDWR|O_NONBLOCK|O_CLOEXEC);
	if (fd<0 || control(fd,VIDIOC_QUERYCAP,&cap)) goto error;
	caps=(cap.capabilities&V4L2_CAP_DEVICE_CAPS) ? cap.device_caps : cap.capabilities;
	printf("driver=%.16s card=%.32s bus=%.32s capabilities=%08x\n",cap.driver,cap.card,cap.bus_info,caps);
	if (!(caps&V4L2_CAP_VIDEO_CAPTURE)) { errno=ENOTSUP; goto error; }
	if (info) {
		for (unsigned i=0;;i++) {
			struct v4l2_fmtdesc desc={.index=i,.type=type};
			if (control(fd,VIDIOC_ENUM_FMT,&desc)) { if (errno==EINVAL) break; goto error; }
			printf("format=%c%c%c%c %.32s\n",desc.pixelformat&255,(desc.pixelformat>>8)&255,
				(desc.pixelformat>>16)&255,(desc.pixelformat>>24)&255,desc.description);
		}
		status=0; goto out;
	}
	if (!(caps&V4L2_CAP_STREAMING)) { errno=ENOTSUP; goto error; }
	format.fmt.pix.width=width; format.fmt.pix.height=height;
	format.fmt.pix.pixelformat=V4L2_PIX_FMT_YUYV; format.fmt.pix.field=V4L2_FIELD_NONE;
	format.fmt.pix.colorspace=V4L2_COLORSPACE_SMPTE170M;
	format.fmt.pix.ycbcr_enc=V4L2_YCBCR_ENC_601;
	format.fmt.pix.quantization=V4L2_QUANTIZATION_LIM_RANGE;
	if (control(fd,VIDIOC_S_FMT,&format)) goto error;
	width=format.fmt.pix.width; height=format.fmt.pix.height;
	if (!width || width>640 || (width&1) || !height || height>480 ||
	    format.fmt.pix.pixelformat!=V4L2_PIX_FMT_YUYV || format.fmt.pix.field!=V4L2_FIELD_NONE ||
	    (format.fmt.pix.ycbcr_enc!=V4L2_YCBCR_ENC_601 && format.fmt.pix.ycbcr_enc!=V4L2_YCBCR_ENC_DEFAULT) ||
	    (format.fmt.pix.ycbcr_enc==V4L2_YCBCR_ENC_DEFAULT && format.fmt.pix.colorspace!=V4L2_COLORSPACE_SMPTE170M &&
	     format.fmt.pix.colorspace!=V4L2_COLORSPACE_SRGB) ||
	    (format.fmt.pix.quantization!=V4L2_QUANTIZATION_DEFAULT &&
	     format.fmt.pix.quantization!=V4L2_QUANTIZATION_LIM_RANGE) ||
	    (format.fmt.pix.quantization==V4L2_QUANTIZATION_DEFAULT && format.fmt.pix.colorspace==V4L2_COLORSPACE_JPEG) ||
	    format.fmt.pix.bytesperline<width*2 || format.fmt.pix.bytesperline>MAX_FRAME ||
	    !format.fmt.pix.sizeimage || format.fmt.pix.sizeimage>MAX_FRAME ||
	    (uint64_t)(height-1)*format.fmt.pix.bytesperline+width*2>format.fmt.pix.sizeimage) {
		errno=ENOTSUP; goto error;
	}
	if (control(fd,VIDIOC_REQBUFS,&request)) goto error;
	allocated=1;
	if (!request.count || request.count>2) { errno=ENOMEM; goto error; }
	for (unsigned i=0;i<request.count;i++) {
		struct v4l2_buffer b={.type=type,.memory=V4L2_MEMORY_MMAP,.index=i};
		if (control(fd,VIDIOC_QUERYBUF,&b)) goto error;
		if (b.length<format.fmt.pix.sizeimage || b.length>MAX_FRAME) { errno=EOVERFLOW; goto error; }
		buffers[i].address=mmap(NULL,b.length,PROT_READ|PROT_WRITE,MAP_SHARED,fd,b.m.offset);
		if (buffers[i].address==MAP_FAILED) goto error;
		buffers[i].length=b.length; mapped++;
		if (control(fd,VIDIOC_QBUF,&b)) goto error;
	}
	if (stopped) { errno=EINTR; goto error; }
	if (control(fd,VIDIOC_STREAMON,&type)) goto error;
	streaming=1;
	now=milliseconds(); if (now<0) goto error;
	deadline=now+10000;
	for (;;) {
		struct pollfd p={.fd=fd,.events=POLLIN};
		struct v4l2_buffer b={.type=type,.memory=V4L2_MEMORY_MMAP};
		int ready;
		if (stopped) { errno=EINTR; goto error; }
		now=milliseconds(); if (now<0) goto error;
		if (now>=deadline) { errno=ETIMEDOUT; goto error; }
		ready=poll(&p,1,(int)(deadline-now));
		if (ready<0 && errno==EINTR) continue;
		if (ready<0) goto error;
		if (!ready) { errno=ETIMEDOUT; goto error; }
		if (p.revents&(POLLERR|POLLHUP|POLLNVAL)) { errno=EIO; goto error; }
		if (!(p.revents&POLLIN)) continue;
		if (control(fd,VIDIOC_DQBUF,&b)) { if (errno==EAGAIN) continue; goto error; }
		if (b.index>=mapped || b.bytesused>buffers[b.index].length) { errno=EOVERFLOW; goto error; }
		if ((b.flags&V4L2_BUF_FLAG_ERROR) || b.bytesused<(uint64_t)(height-1)*format.fmt.pix.bytesperline+width*2) {
			if (control(fd,VIDIOC_QBUF,&b)) goto error;
			continue;
		}
		if (bmp_save_yuyv(argv[3],buffers[b.index].address,b.bytesused,width,height,format.fmt.pix.bytesperline)) goto error;
		printf("Saved %ux%u YUYV as BMP: %s\n",width,height,argv[3]);
		status=0; break;
	}
	goto out;
error:
	saved=errno; perror("camera");
out:
	/* close() is the final release path even if a detached driver rejects OFF. */
	if (streaming && ioctl(fd,VIDIOC_STREAMOFF,&type)<0) { perror("STREAMOFF"); status=1; }
	for (unsigned i=0;i<mapped;i++) if (munmap(buffers[i].address,buffers[i].length)) { perror("munmap"); status=1; }
	if (allocated) {
		request.count=0;
		if (ioctl(fd,VIDIOC_REQBUFS,&request)<0) { perror("release buffers"); status=1; }
	}
	if (fd>=0) close(fd);
	if (saved) errno=saved;
	return status;
}
