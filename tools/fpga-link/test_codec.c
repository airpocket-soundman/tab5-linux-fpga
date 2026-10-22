/* SPDX-License-Identifier: GPL-2.0-only */
/* Host-only harness for the unchanged, separately attributed vendor header. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "vendor/link_protocol.h"

static int decode(const char *text, uint8_t frame[8])
{
    if (strlen(text) != 16) return 0;
    for (unsigned i = 0; i < 8; ++i) {
        unsigned value;
        if (sscanf(text + i * 2, "%2x", &value) != 1) return 0;
        frame[i] = (uint8_t)value;
    }
    return 1;
}

int main(void)
{
    char request_hex[17], response_hex[17];
    int expected;
    unsigned cases = 0;
    if (link_crc16((const uint8_t *)"123456789", 9) != 0x29b1) return 1;
    while (scanf("%16s %16s %d", request_hex, response_hex, &expected) == 3) {
        uint8_t request[8], response[8], generated[8];
        if (!decode(request_hex, request) || !decode(response_hex, response)) return 2;
        if (link_validate_response(response, request) != (expected != 0)) return 3;
        if (request[0] == 0xa5 && request[3] == 2 &&
            link_crc16(request, 6) == (uint16_t)(request[6] | request[7] << 8)) {
            link_make_request(generated, request[1], request[2], request[4], request[5]);
            if (memcmp(request, generated, 8)) return 4;
        }
        ++cases;
    }
    printf("C codec cases=%u\n", cases);
    return cases == 583 ? 0 : 5;
}
