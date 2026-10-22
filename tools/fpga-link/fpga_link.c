/* SPDX-License-Identifier: GPL-2.0-only */
/* CPython-free bringup-v0 mock CLI. Application code uses bounded buffers
 * and no heap allocation. See SOURCE.json for the unchanged vendor codec's
 * provenance and undeclared upstream license; this SPDX applies here only.
 */
#include <stdio.h>
#include <string.h>
#include "vendor/link_protocol.h"

enum { FRAME_BYTES = 8, OP_ID = 1, OP_ECHO = 2, OP_INVERT = 3 };

/* Byte-level mock endpoint, independently implemented from the Python mock.
 * This does not model electrical direction, clocks, READY/OE or DDR3.
 */
static int mock_exchange(const uint8_t request[8], uint8_t response[8])
{
    uint16_t crc = link_crc16(request, 6);
    response[0] = 0x5a;
    response[1] = 0;
    response[2] = request[2];
    response[3] = 2;
    response[4] = 0;
    response[5] = 0;
    if (request[0] != 0xa5 || request[3] != 2 ||
        request[6] != (uint8_t)crc || request[7] != (uint8_t)(crc >> 8)) {
        response[1] = 1;
    } else {
        switch (request[1]) {
        case OP_ID:
            response[4] = 'T'; response[5] = 'P';
            break;
        case OP_ECHO:
            response[4] = request[4]; response[5] = request[5];
            break;
        case OP_INVERT:
            response[4] = (uint8_t)(request[4] ^ 0xff);
            response[5] = (uint8_t)(request[5] ^ 0xff);
            break;
        default:
            response[1] = 2;
            break;
        }
    }
    crc = link_crc16(response, 6);
    response[6] = (uint8_t)crc;
    response[7] = (uint8_t)(crc >> 8);
    return 0;
}

/* Complete-frame transport boundary, not the Python streaming/deadline API.
 * Only this deterministic nonblocking mock backend exists in the C CLI.
 */
struct transport {
    int (*exchange)(const uint8_t request[8], uint8_t response[8]);
};

static int transact(const struct transport *transport, uint8_t *sequence,
                    uint8_t opcode, uint8_t first, uint8_t second,
                    uint8_t request[8], uint8_t response[8])
{
    link_make_request(request, opcode, *sequence, first, second);
    *sequence = (uint8_t)(*sequence + 1u);
    if (transport->exchange(request, response)) return 1;
    return link_validate_response(response, request) ? 0 : 1;
}

static void print_hex(const uint8_t frame[8])
{
    for (unsigned i = 0; i < FRAME_BYTES; ++i) printf("%02x", frame[i]);
}

static void print_result(const uint8_t request[8], const uint8_t response[8])
{
    printf("{\"backend\":\"mock\",\"physical_link_tested\":false,\"request\":\"");
    print_hex(request);
    printf("\",\"response\":\"");
    print_hex(response);
    printf("\",\"result\":[%u,%u],\"host_accept\":%s}\n",
           (unsigned)response[4], (unsigned)response[5],
           link_validate_response(response, request) ? "true" : "false");
}

static int hex_digit(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

static int parse_byte(const char *text, uint8_t *result)
{
    unsigned value = 0, base = 10;
    if (text[0] == '0' && (text[1] == 'x' || text[1] == 'X')) {
        base = 16;
        text += 2;
    }
    if (!*text) return 1;
    for (; *text; ++text) {
        int digit = hex_digit(*text);
        if (digit < 0 || (unsigned)digit >= base) return 1;
        value = value * base + (unsigned)digit;
        if (value > 255) return 1;
    }
    *result = (uint8_t)value;
    return 0;
}

static int decode_frame(const char *text, uint8_t frame[8])
{
    if (strlen(text) != 16) return 1;
    for (unsigned i = 0; i < FRAME_BYTES; ++i) {
        int high = hex_digit(text[i * 2]), low = hex_digit(text[i * 2 + 1]);
        if (high < 0 || low < 0) return 1;
        frame[i] = (uint8_t)((unsigned)high * 16u + (unsigned)low);
    }
    return 0;
}

static int run_selftest(const struct transport *transport)
{
    uint8_t sequence = 0, request[8], response[8];
    if (link_crc16((const uint8_t *)"123456789", 9) != 0x29b1) return 1;
    if (transact(transport, &sequence, OP_ID, 0, 0, request, response)) return 1;
    for (unsigned value = 0; value < 256; ++value) {
        if (transact(transport, &sequence, OP_ECHO, (uint8_t)value,
                     (uint8_t)(value ^ 0xa5), request, response)) return 1;
        if (transact(transport, &sequence, OP_INVERT, (uint8_t)value,
                     (uint8_t)(255u - value), request, response)) return 1;
    }
    puts("{\"backend\":\"mock\",\"physical_link_tested\":false,\"mock_transactions\":513}");
    return 0;
}

/* Test-only stdin interface: one exact hex request per line, including bad
 * CRC/format cases. Python compares each mock reply to the shared fixtures.
 */
static int run_vectors(const struct transport *transport)
{
    char line[32];
    uint8_t request[8], response[8];
    while (fgets(line, sizeof(line), stdin)) {
        line[strcspn(line, "\r\n")] = '\0';
        if (decode_frame(line, request)) return 2;
        if (transport->exchange(request, response)) return 1;
        print_result(request, response);
    }
    return ferror(stdin) ? 1 : 0;
}

static int usage(void)
{
    fputs("Usage: fpga-link --mock id|selftest\n"
          "       fpga-link --mock echo|invert BYTE BYTE\n"
          "       fpga-link --mock --vectors < hex-requests.txt\n", stderr);
    return 2;
}

int main(int argc, char **argv)
{
    const struct transport transport = { .exchange = mock_exchange };
    uint8_t sequence = 0, opcode, first = 0, second = 0;
    uint8_t request[8], response[8];
    if (argc < 3 || strcmp(argv[1], "--mock")) return usage();
    if (argc == 3 && !strcmp(argv[2], "selftest")) return run_selftest(&transport);
    if (argc == 3 && !strcmp(argv[2], "--vectors")) return run_vectors(&transport);
    if (argc == 3 && !strcmp(argv[2], "id")) {
        opcode = OP_ID;
    } else if (argc == 5 && (!strcmp(argv[2], "echo") || !strcmp(argv[2], "invert"))) {
        opcode = !strcmp(argv[2], "echo") ? OP_ECHO : OP_INVERT;
        if (parse_byte(argv[3], &first) || parse_byte(argv[4], &second)) return usage();
    } else {
        return usage();
    }
    if (transact(&transport, &sequence, opcode, first, second, request, response)) {
        fputs("Mock transaction failed\n", stderr);
        return 1;
    }
    print_result(request, response);
    return 0;
}
