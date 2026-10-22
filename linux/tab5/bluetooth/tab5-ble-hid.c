// SPDX-License-Identifier: GPL-2.0-only
/*
 * Minimal single-process Linux BLE keyboard host for NOMMU Tab5.
 * Uses the Linux Bluetooth management protocol, ATT fixed channel and UHID.
 * No BlueZ daemon, fork, threads, D-Bus, dlopen or third-party library.
 * Initial experimental scope: one HID service, standard 16-bit GATT UUIDs,
 * authenticated pairing with DisplayOnly IO capability, input notifications.
 * Bond keys are kept by the running kernel only, never printed or persisted.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>
#include <linux/input.h>
#include <linux/uhid.h>

#ifndef AF_BLUETOOTH
#define AF_BLUETOOTH 31
#endif
#define SOL_BT 274
#define BT_SECURITY_OPT 4
#define PROTO_L2CAP 0
#define PROTO_HCI 1
#define MAX_CHARS 64
struct hci_address { sa_family_t family; uint16_t dev, channel; };
struct l2_address { sa_family_t family; uint16_t psm; uint8_t addr[6]; uint16_t cid; uint8_t type; };
struct characteristic { uint16_t declaration, value, uuid, end, ccc; uint8_t id, kind; };
static struct characteristic chars[MAX_CHARS];
static unsigned nchar;
static int mgmt_fd = -1, att_fd = -1, uhid_fd = -1;
static uint16_t controller;
static uint8_t pairing_peer[7];
static int pairing_active;
static int scan_finished;
static int input_started, input_numbered;
static volatile sig_atomic_t stopping;
static struct uhid_event uevent;
static uint8_t report_map[HID_MAX_DESCRIPTOR_SIZE];
static int forward_notification(const uint8_t *b, size_t len);

static uint16_t le16(const void *p) { const uint8_t *b=p; return b[0] | (uint16_t)b[1]<<8; }
static uint32_t le32(const void *p) { const uint8_t *b=p; return le16(b) | (uint32_t)le16(b+2)<<16; }
static void put16(void *p, uint16_t v) { uint8_t *b=p; b[0]=v; b[1]=v>>8; }
static void on_signal(int sig) { (void)sig; stopping=1; }
static int readable(int fd, int timeout) {
 struct pollfd p={.fd=fd,.events=POLLIN};
 int n; do n=poll(&p,1,timeout); while (n<0 && errno==EINTR && !stopping);
 return n>0 && (p.revents&POLLIN);
}
static int mgmt_send(uint16_t op, const uint8_t *data, size_t len) {
 uint8_t b[128];
 if (len>sizeof(b)-6) { errno=EMSGSIZE; return -1; }
 put16(b,op); put16(b+2,controller); put16(b+4,len);
 if (len) memcpy(b+6,data,len);
 return send(mgmt_fd,b,len+6,0)==(ssize_t)len+6 ? 0:-1;
}
/* Deal only with the selected controller; never print key material. */
static void mgmt_event(uint16_t event, const uint8_t *b, size_t len) {
 if (event==0x0013 && len==2 && b[0]==6 && b[1]<=1) {
  scan_finished=!b[1];
  return;
 }
 if (!pairing_active || len<7 || memcmp(b,pairing_peer,7)) return;
 if (event==0x0017 && len>=12) {
  printf("Enter passkey %06u on the keyboard and press Enter (%u digits entered).\n",
   (unsigned)le32(b+7),b[11]); fflush(stdout);
 } else if (event==0x000f && len>=12) {
  if (b[7]) {
   /* Kernel explicitly marks this as Just Works, with no numeric comparison. */
   fprintf(stderr,"Unauthenticated Just Works pairing is unsupported.\n");
   mgmt_send(0x001d,b,7);
  } else {
   char answer[16];
   printf("Compare passkey %06u on both devices. Type yes only if equal: ",
    (unsigned)le32(b+8)); fflush(stdout);
   if (fgets(answer,sizeof(answer),stdin) && !strcmp(answer,"yes\n"))
    mgmt_send(0x001c,b,7);
   else mgmt_send(0x001d,b,7);
  }
 } else if (event==0x0010 && len>=7) {
  /* This host has no keyboard-entry agent; report an explicit rejection. */
  fprintf(stderr,"Peer requested host passkey entry; unsupported in this build.\n");
  mgmt_send(0x001f,b,7);
 }
}
static int mgmt_command(uint16_t op, const uint8_t *data, size_t len, int seconds) {
 uint8_t b[1024]; time_t until=time(NULL)+seconds;
 if (mgmt_send(op,data,len)<0) return -1;
 while (!stopping && time(NULL)<until) {
  if (!readable(mgmt_fd,500)) continue;
  ssize_t n=recv(mgmt_fd,b,sizeof(b),0);
  if (n<6 || le16(b+2)!=controller || le16(b+4)>(size_t)n-6) continue;
  size_t count=le16(b+4); uint16_t event=le16(b);
  if (event==1 && count>=3 && le16(b+6)==op) {
   if (b[8] && !(op==0x0024 && b[8]==0x0b)) {
    fprintf(stderr,"MGMT command 0x%04x failed, status 0x%02x\n",op,b[8]); errno=EIO; return -1;
   }
   return 0;
  }
  if (event==2 && count>=3 && le16(b+6)==op && b[8]) {
   if (op==0x0024 && b[8]==0x0b) return 0; /* Already stopped: idempotent cleanup. */
   fprintf(stderr,"MGMT command 0x%04x rejected, status 0x%02x\n",op,b[8]); errno=EIO; return -1;
  }
  mgmt_event(event,b+6,count);
 }
 errno=ETIMEDOUT; return -1;
}
static int open_controller(void) {
 struct hci_address a={.family=AF_BLUETOOTH,.dev=0xffff,.channel=3};
 mgmt_fd=socket(AF_BLUETOOTH,SOCK_RAW|SOCK_CLOEXEC,PROTO_HCI);
 if (mgmt_fd<0 || bind(mgmt_fd,(void*)&a,sizeof(a))<0) return -1;
 uint8_t yes=1, display_only=0;
 if (mgmt_command(0x000d,&yes,1,10)<0 || mgmt_command(5,&yes,1,20)<0 ||
     mgmt_command(9,&yes,1,10)<0 || mgmt_command(0x0018,&display_only,1,10)<0) return -1;
 return 0;
}
static int scan(const char *wanted) {
 uint8_t kind=6,b[1024]; time_t until=time(NULL)+20;
 scan_finished=0;
 if (mgmt_command(0x0023,&kind,1,10)<0) return -1;
 printf("Scanning BLE for 20 seconds, name filter: %s\n",wanted); fflush(stdout);
 while (!stopping && !scan_finished && time(NULL)<until) {
  if (!readable(mgmt_fd,500)) continue;
  ssize_t n=recv(mgmt_fd,b,sizeof(b),0);
  if (n<6 || le16(b+2)!=controller || le16(b+4)>(size_t)n-6) continue;
  mgmt_event(le16(b),b+6,le16(b+4));
  if (scan_finished) return 0;
  if (n<20 || le16(b)!=0x0012 ||
      le16(b+4)<14 || le16(b+4)>(size_t)n-6) continue;
  const uint8_t *p=b+6; size_t eir=le16(p+12);
  if (eir>(size_t)le16(b+4)-14) continue;
  char name[249]={0};
  for (size_t i=0;i<eir;) {
   size_t size=p[14+i]; if (!size || i+size+1>eir) break;
   if ((p[15+i]==8 || p[15+i]==9) && size>1) {
    size_t k=size-1; if (k>=sizeof(name)) k=sizeof(name)-1;
    memcpy(name,p+16+i,k); name[k]=0;
    for (size_t j=0;j<k;j++) if ((unsigned char)name[j]<32 || name[j]==127) name[j]='?';
   }
   i+=size+1;
  }
  if (*wanted && !strstr(name,wanted)) continue;
  printf("%02X:%02X:%02X:%02X:%02X:%02X %s %s\n",p[5],p[4],p[3],p[2],p[1],p[0],
   p[6]==1?"public":"random",name); fflush(stdout);
 }
 return scan_finished?0:mgmt_command(0x0024,&kind,1,10);
}
static int att_request(const uint8_t *request, size_t len, uint8_t *reply, size_t cap) {
 if (send(att_fd,request,len,0)!=(ssize_t)len) return -1;
 time_t until=time(NULL)+10;
 while (!stopping && time(NULL)<until) {
  if (!readable(att_fd,500)) continue;
  ssize_t n=recv(att_fd,reply,cap,0);
  if (n<1) return -1;
  if (reply[0]==0x1b || reply[0]==0x1d) {
   if (forward_notification(reply,n)<0) return -1;
   continue;
  }
  return n;
 }
 errno=ETIMEDOUT; return -1;
}
static int discover_hid(uint16_t *start, uint16_t *end) {
 uint8_t q[7]={0x10,1,0,0xff,0xff,0,0x28},r[512];
 for (uint16_t pos=1;pos;) {
  put16(q+1,pos); int n=att_request(q,sizeof(q),r,sizeof(r));
  if (n<2 || r[0]!=0x11 || (r[1]!=6 && r[1]!=20)) return -1;
  unsigned step=r[1]; uint16_t last=0;
  for (unsigned i=2;i+step<=(unsigned)n;i+=step) {
   last=le16(r+i+2);
   if (step==6 && le16(r+i+4)==0x1812) { *start=le16(r+i); *end=last; return 0; }
  }
  if (!last || last==0xffff || last<pos) break;
  pos=last+1;
 }
 return -1;
}
static int discover_chars(uint16_t start, uint16_t end) {
 uint8_t q[7]={8,0,0,0,0,3,0x28},r[512]; uint16_t pos=start;
 nchar=0; put16(q+3,end);
 while (pos<=end) {
  put16(q+1,pos); int n=att_request(q,sizeof(q),r,sizeof(r));
  if (n>=5 && r[0]==1 && r[4]==0x0a) break;
  if (n<2 || r[0]!=9 || (r[1]!=7 && r[1]!=21)) return -1;
  unsigned step=r[1]; uint16_t last=0;
  for (unsigned i=2;i+step<=(unsigned)n;i+=step) {
   last=le16(r+i);
   if (nchar==MAX_CHARS) return -1;
   if (nchar) chars[nchar-1].end=last-1;
   chars[nchar++]=(struct characteristic){.declaration=last,.value=le16(r+i+3),
    .uuid=step==7?le16(r+i+5):0,.end=end};
  }
  if (!last || last==0xffff || last<pos) break;
  pos=last+1;
 }
 return nchar?0:-1;
}
static int read_value(uint16_t handle, uint8_t *data, size_t cap) {
 uint8_t q[5]={0x0a,0,0,0,0},r[512]; size_t done=0;
 put16(q+1,handle);
 while (done<cap) {
  int n=att_request(q,done?5:3,r,sizeof(r));
  if (n>=5 && r[0]==1 && done && r[4]==7) return done;
  if (n<1 || r[0]!=(done?0x0d:0x0b) || (size_t)(n-1)>cap-done) return -1;
  memcpy(data+done,r+1,n-1); done+=n-1;
  if (n<23) return done;
  q[0]=0x0c; put16(q+3,done);
 }
 return -1;
}
static int discover_descriptors(struct characteristic *c) {
 uint8_t q[5]={4,0,0,0,0},r[512]; uint16_t pos=c->value+1;
 put16(q+3,c->end);
 while (pos<=c->end) {
  put16(q+1,pos); int n=att_request(q,5,r,sizeof(r));
  if (n>=5 && r[0]==1 && r[4]==0x0a) break;
  if (n<2 || r[0]!=5 || (r[1]!=1 && r[1]!=2)) return -1;
  unsigned step=r[1]==1?4:18; uint16_t last=0;
  for (unsigned i=2;i+step<=(unsigned)n;i+=step) {
   last=le16(r+i);
   if (step==4 && le16(r+i+2)==0x2902) c->ccc=last;
   if (step==4 && le16(r+i+2)==0x2908) {
    uint8_t ref[8]; int size=read_value(last,ref,sizeof(ref));
    if (size!=2) return -1;
    c->id=ref[0]; c->kind=ref[1];
   }
  }
  if (!last || last==0xffff || last<pos) break;
  pos=last+1;
 }
 return 0;
}
static int uhid_event(void) {
 ssize_t n=read(uhid_fd,&uevent,sizeof(uevent));
 if (n<4) return -1;
 if (uevent.type==UHID_START) {
  if (n<(ssize_t)(sizeof(uevent.type)+sizeof(uevent.u.start))) { errno=EPROTO; return -1; }
  input_numbered=!!(uevent.u.start.dev_flags&UHID_DEV_NUMBERED_INPUT_REPORTS);
  input_started=1;
 } else if (uevent.type==UHID_STOP) {
  input_started=0; errno=ENODEV; return -1;
 } else if (uevent.type==UHID_GET_REPORT || uevent.type==UHID_SET_REPORT) {
  int get=uevent.type==UHID_GET_REPORT;
  uint32_t id=get?uevent.u.get_report.id:uevent.u.set_report.id;
  memset(&uevent,0,sizeof(uevent));
  if (get) {
   uevent.type=UHID_GET_REPORT_REPLY;
   uevent.u.get_report_reply.id=id; uevent.u.get_report_reply.err=EOPNOTSUPP;
  } else {
   uevent.type=UHID_SET_REPORT_REPLY;
   uevent.u.set_report_reply.id=id; uevent.u.set_report_reply.err=EOPNOTSUPP;
  }
  if (write(uhid_fd,&uevent,sizeof(uevent))!=(ssize_t)sizeof(uevent)) return -1;
 }
 return 0;
}
static int create_input(int map_size) {
 uhid_fd=open("/dev/uhid",O_RDWR|O_CLOEXEC|O_NONBLOCK);
 if (uhid_fd<0) return -1;
 memset(&uevent,0,sizeof(uevent)); uevent.type=UHID_CREATE2;
 snprintf((char*)uevent.u.create2.name,sizeof(uevent.u.create2.name),"Tab5 BLE keyboard");
 snprintf((char*)uevent.u.create2.phys,sizeof(uevent.u.create2.phys),"esp-hosted-le");
 uevent.u.create2.bus=BUS_BLUETOOTH;
 uevent.u.create2.rd_size=map_size;
 memcpy(uevent.u.create2.rd_data,report_map,map_size);
 if (write(uhid_fd,&uevent,sizeof(uevent))!=(ssize_t)sizeof(uevent)) return -1;
 time_t until=time(NULL)+10;
 while (!stopping && !input_started && time(NULL)<until) {
  if (readable(uhid_fd,500) && uhid_event()<0) return -1;
 }
 if (!input_started) { errno=ETIMEDOUT; return -1; }
 return 0;
}
static int notifications(void) {
 unsigned inputs=0;
 for (unsigned i=0;i<nchar;i++) {
  if (chars[i].uuid!=0x2a4d || chars[i].kind!=1 || !chars[i].ccc) continue;
  uint8_t q[5]={0x12,0,0,1,0},r[512]; put16(q+1,chars[i].ccc);
  int n=att_request(q,5,r,sizeof(r));
  if (n!=1 || r[0]!=0x13) return -1;
  inputs++;
 }
 return inputs?0:-1;
}
static int forward_notification(const uint8_t *b, size_t len) {
 if (len<3) { errno=EPROTO; return -1; }
 uint16_t handle=le16(b+1);
 if (uhid_fd>=0) for (unsigned i=0;i<nchar;i++) if (chars[i].value==handle && chars[i].kind==1) {
  memset(&uevent,0,sizeof(uevent)); uevent.type=UHID_INPUT2;
  if (!input_started || (!!chars[i].id)!=input_numbered) { errno=EPROTO; return -1; }
  size_t off=input_numbered?1:0;
  if (len-3+off>sizeof(uevent.u.input2.data)) { errno=EMSGSIZE; return -1; }
  if (off) uevent.u.input2.data[0]=chars[i].id;
  memcpy(uevent.u.input2.data+off,b+3,len-3); uevent.u.input2.size=len-3+off;
  if (write(uhid_fd,&uevent,sizeof(uevent))!=(ssize_t)sizeof(uevent)) return -1;
 }
 if (b[0]==0x1d) { uint8_t ack=0x1e; if (send(att_fd,&ack,1,0)!=1) return -1; }
 return 0;
}
static int input_loop(void) {
 uint8_t b[1024];
 puts("BLE HID input active. Keep this process running; Ctrl-C disconnects."); fflush(stdout);
 while (!stopping) {
  struct pollfd p[3]={{att_fd,POLLIN,0},{uhid_fd,POLLIN,0},{mgmt_fd,POLLIN,0}};
  int result=poll(p,3,1000);
  if (result<0) { if (errno==EINTR) continue; return -1; }
  if (p[0].revents&(POLLHUP|POLLERR)) return -1;
  if (p[0].revents&POLLIN) {
   ssize_t n=recv(att_fd,b,sizeof(b),0); if (n<=0) return -1;
   if (n<3 || (b[0]!=0x1b && b[0]!=0x1d)) continue;
   if (forward_notification(b,n)<0) return -1;
  }
  if ((p[1].revents&POLLIN) && uhid_event()<0) return -1;
  if (p[2].revents&POLLIN) {
   ssize_t n=recv(mgmt_fd,b,sizeof(b),0);
   if (n>=6 && le16(b+2)==controller && le16(b+4)<=(size_t)n-6) mgmt_event(le16(b),b+6,le16(b+4));
  }
 }
 return 0;
}
static int connect_keyboard(const char *address, const char *kind) {
 uint8_t peer[8]={0}; unsigned a[6]; int consumed=0;
 if (sscanf(address,"%2x:%2x:%2x:%2x:%2x:%2x%n",a,a+1,a+2,a+3,a+4,a+5,&consumed)!=6 ||
     address[consumed]) { errno=EINVAL; return -1; }
 for (unsigned i=0;i<6;i++) peer[5-i]=a[i];
 if (!strcmp(kind,"public")) peer[6]=1;
 else if (!strcmp(kind,"random")) peer[6]=2;
 else { errno=EINVAL; return -1; }
 puts("Pairing: keyboard may require typing the displayed passkey."); fflush(stdout);
 memcpy(pairing_peer,peer,7); pairing_active=1;
 if (mgmt_command(0x0019,peer,sizeof(peer),90)<0) return -1;
 pairing_active=0;
 struct l2_address local={.family=AF_BLUETOOTH,.cid=4,.type=1};
 struct l2_address remote={.family=AF_BLUETOOTH,.cid=4,.type=peer[6]};
 memcpy(remote.addr,peer,6);
 att_fd=socket(AF_BLUETOOTH,SOCK_SEQPACKET|SOCK_CLOEXEC,PROTO_L2CAP);
 uint8_t security[2]={3,0}; /* BT_SECURITY_HIGH: authenticated encryption. */
 if (att_fd<0 || setsockopt(att_fd,SOL_BT,BT_SECURITY_OPT,security,2)<0 ||
     bind(att_fd,(void*)&local,sizeof(local))<0 || connect(att_fd,(void*)&remote,sizeof(remote))<0) return -1;
 uint16_t start,end; int map_size=-1;
 if (discover_hid(&start,&end)<0 || discover_chars(start,end)<0) { errno=EPROTO; return -1; }
 for (unsigned i=0;i<nchar;i++) {
  if (chars[i].uuid==0x2a4e) {
   uint8_t report_mode[4]={0x52,0,0,1}; put16(report_mode+1,chars[i].value);
   if (send(att_fd,report_mode,4,0)!=4) return -1;
  }
  if (chars[i].uuid==0x2a4b) map_size=read_value(chars[i].value,report_map,sizeof(report_map));
  if (chars[i].uuid==0x2a4d && discover_descriptors(chars+i)<0) { errno=EPROTO; return -1; }
 }
 if (map_size<=0 || create_input(map_size)<0 || notifications()<0) { errno=EPROTO; return -1; }
 return input_loop();
}
int main(int argc,char **argv) {
 if (argc==2 && !strcmp(argv[1],"--version")) { puts("tab5-ble-hid experimental 0.1"); return 0; }
 if (argc<2 || (strcmp(argv[1],"scan") && strcmp(argv[1],"connect"))) {
  fprintf(stderr,"Usage: %s scan [name] | connect MAC public|random\n",argv[0]); return 2;
 }
 if (!strcmp(argv[1],"connect") && argc!=4) return 2;
 signal(SIGINT,on_signal); signal(SIGTERM,on_signal);
 if (open_controller()<0) { perror("Bluetooth controller (requires root and BLE kernel/module)"); return 1; }
 int rc=!strcmp(argv[1],"scan")?scan(argc>2?argv[2]:"K68"):connect_keyboard(argv[2],argv[3]);
 if (rc<0) perror("BLE host");
 if (uhid_fd>=0) close(uhid_fd);
 if (att_fd>=0) close(att_fd);
 if (mgmt_fd>=0) close(mgmt_fd);
 return rc<0?1:0;
}
