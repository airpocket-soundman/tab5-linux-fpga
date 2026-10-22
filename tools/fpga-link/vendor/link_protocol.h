#pragma once
#include <stdbool.h>
#include <stdint.h>

// Pure bringup-v0 codec: shared by the device firmware and desktop tests.
static inline uint16_t link_crc16(const uint8_t *p, unsigned n) {
    uint16_t c=0xffff;
    while(n--) { c^=(uint16_t)*p++ << 8; for(int i=0;i<8;i++) c=(c&0x8000)?(c<<1)^0x1021:c<<1; }
    return c;
}
static inline void link_make_request(uint8_t q[8], uint8_t op, uint8_t seq, uint8_t a, uint8_t b) {
    q[0]=0xa5; q[1]=op; q[2]=seq; q[3]=2; q[4]=a; q[5]=b;
    uint16_t c=link_crc16(q,6); q[6]=(uint8_t)c; q[7]=(uint8_t)(c>>8);
}
static inline bool link_validate_response(const uint8_t r[8], const uint8_t q[8]) {
    uint16_t c=link_crc16(r,6);
    if(r[0]!=0x5a || r[1]!=0 || r[2]!=q[2] || r[3]!=2 || r[6]!=(uint8_t)c || r[7]!=(uint8_t)(c>>8)) return false;
    switch(q[1]) {
        case 1: return r[4]=='T' && r[5]=='P';
        case 2: return r[4]==q[4] && r[5]==q[5];
        case 3: return r[4]==(uint8_t)(q[4]^255) && r[5]==(uint8_t)(q[5]^255);
        default: return false;
    }
}
