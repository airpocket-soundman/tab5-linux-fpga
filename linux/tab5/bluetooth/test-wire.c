// SPDX-License-Identifier: GPL-2.0-only
/* Offline protocol fixtures: Unix socket pairs only, no Bluetooth hardware. */
#define main ble_program_main
#include "tab5-ble-hid.c"
#undef main
#include <assert.h>

int main(void) {
 int pair[2]; assert(socketpair(AF_UNIX,SOCK_SEQPACKET,0,pair)==0);
 mgmt_fd=pair[0];
 uint8_t rejected[]={2,0,0,0,3,0,5,0,0x0c};
 assert(send(pair[1],rejected,sizeof(rejected),0)==sizeof(rejected));
 assert(mgmt_command(5,NULL,0,1)<0 && errno==EIO);
 uint8_t completed[]={1,0,0,0,3,0,5,0,0};
 assert(send(pair[1],completed,sizeof(completed),0)==sizeof(completed));
 assert(mgmt_command(5,NULL,0,1)==0);
 uint8_t discard[64];
 assert(recv(pair[1],discard,sizeof(discard),0)==6);
 assert(recv(pair[1],discard,sizeof(discard),0)==6);
 mgmt_fd=-1;
 att_fd=pair[0];
 uint8_t service[]={0x11,6,1,0,20,0,0x12,0x18};
 assert(send(pair[1],service,sizeof(service),0)==sizeof(service));
 uint16_t start=0,end=0;
 assert(discover_hid(&start,&end)==0 && start==1 && end==20);

 uint8_t declarations[]={9,7,2,0,2,3,0,0x4b,0x2a,4,0,0x10,5,0,0x4d,0x2a,8,0,4,9,0,0x4e,0x2a};
 uint8_t exhausted[]={1,8,9,0,0x0a};
 assert(send(pair[1],declarations,sizeof(declarations),0)==sizeof(declarations));
 assert(send(pair[1],exhausted,sizeof(exhausted),0)==sizeof(exhausted));
 assert(discover_chars(start,end)==0 && nchar==3);
 assert(chars[0].value==3 && chars[0].end==3 && chars[0].uuid==0x2a4b);
 assert(chars[1].value==5 && chars[1].end==7 && chars[1].uuid==0x2a4d);
 uint8_t descriptors[]={5,1,6,0,2,0x29,7,0,8,0x29};
 uint8_t reference[]={0x0b,1,1};
 assert(send(pair[1],descriptors,sizeof(descriptors),0)==sizeof(descriptors));
 assert(send(pair[1],reference,sizeof(reference),0)==sizeof(reference));
 assert(discover_descriptors(chars+1)==0);
 assert(chars[1].ccc==6 && chars[1].id==1 && chars[1].kind==1);

 uint8_t chunk[23]={0x0b},tail[]={0x0d,0x55},result[64];
 for (unsigned i=1;i<sizeof(chunk);i++) chunk[i]=i;
 assert(send(pair[1],chunk,sizeof(chunk),0)==sizeof(chunk));
 assert(send(pair[1],tail,sizeof(tail),0)==sizeof(tail));
 assert(read_value(3,result,sizeof(result))==23 && result[0]==1 && result[22]==0x55);

 FILE *file=tmpfile(); assert(file); uhid_fd=fileno(file);
 input_started=1; input_numbered=1;
 uint8_t keys[]={0x1b,5,0,2,0,4,0,0,0,0,0};
 assert(forward_notification(keys,sizeof(keys))==0);
 assert(lseek(uhid_fd,0,SEEK_SET)==0);
 struct uhid_event observed;
 assert(read(uhid_fd,&observed,sizeof(observed))==sizeof(observed));
 assert(observed.type==UHID_INPUT2 && observed.u.input2.size==9);
 assert(observed.u.input2.data[0]==1 && observed.u.input2.data[1]==2 && observed.u.input2.data[3]==4);
 input_numbered=0;
 assert(forward_notification(keys,sizeof(keys))<0 && errno==EPROTO);
 chars[1].id=0;
 assert(forward_notification(keys,sizeof(keys))==0);
 assert(lseek(uhid_fd,sizeof(observed),SEEK_SET)==sizeof(observed));
 assert(read(uhid_fd,&observed,sizeof(observed))==sizeof(observed));
 assert(observed.u.input2.size==8 && observed.u.input2.data[0]==2);
 uint8_t malformed[]={0x1b,5};
 assert(forward_notification(malformed,sizeof(malformed))<0);
 fclose(file); uhid_fd=-1;
 close(pair[0]); close(pair[1]); att_fd=-1;
 puts("PASS: MGMT status/complete, HID discovery, long read, numbered/unnumbered UHID input, malformed notification");
 return 0;
}
