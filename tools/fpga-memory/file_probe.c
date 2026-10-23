/* SPDX-License-Identifier: GPL-2.0-only */
/* Host file mock only. No physical transport, external path or device backend. */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define MAX_SIZE (UINT64_C(128) * 1024 * 1024)
#define BUFFER_SIZE 65536u

static uint32_t crc_update(uint32_t crc, const unsigned char *data, size_t size)
{
    for (size_t i = 0; i < size; ++i) {
        crc ^= data[i];
        for (unsigned bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ (UINT32_C(0xedb88320) & (0u - (crc & 1u)));
    }
    return crc;
}

static unsigned char pattern(uint64_t address, unsigned pass)
{
    /* The supported address range fits uint32_t. Unsigned wrap is intentional. */
    uint32_t x = (uint32_t)address ^
        (pass == 0 ? UINT32_C(0x9e3779b9) : UINT32_C(0x85ebca6b));
    x ^= x >> 16;
    x *= UINT32_C(0x7feb352d);
    x ^= x >> 15;
    x *= UINT32_C(0x846ca68b);
    x ^= x >> 16;
    return (unsigned char)(x & 255u);
}

static int number(const char *text, uint64_t maximum, uint64_t *result)
{
    uint64_t value = 0;
    if (!*text) return 0;
    for (; *text; ++text) {
        if (*text < '0' || *text > '9') return 0;
        unsigned digit = (unsigned)(*text - '0');
        if (value > maximum / 10 ||
            (value == maximum / 10 && digit > maximum % 10)) return 0;
        value = value * 10 + digit;
    }
    *result = value;
    return 1;
}

static int seek_file(FILE *file, uint64_t address)
{
    /* File extent <=128 MiB; every offset fits a 32-bit signed long. */
    return fseek(file, (long)address, SEEK_SET);
}

static int usage(void)
{
    fputs("usage: file-probe --mock [--size 1..134217728] [--chunk 1..65536] "
          "[--inject-corruption byte-offset]\n", stderr);
    return 2;
}

int main(int argc, char **argv)
{
    uint64_t size = 1024 * 1024 + 17, chunk = 4096, corrupt_at = 0;
    int mock = 0, inject = 0;
    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--mock")) mock = 1;
        else if (!strcmp(argv[i], "--size") && i + 1 < argc) {
            if (!number(argv[++i], MAX_SIZE, &size) || !size) return usage();
        } else if (!strcmp(argv[i], "--chunk") && i + 1 < argc) {
            if (!number(argv[++i], BUFFER_SIZE, &chunk) || !chunk) return usage();
        } else if (!strcmp(argv[i], "--inject-corruption") && i + 1 < argc) {
            if (!number(argv[++i], MAX_SIZE - 1, &corrupt_at)) return usage();
            inject = 1;
        } else return usage();
    }
    if (!mock || (inject && corrupt_at >= size)) return usage();
    if ((crc_update(UINT32_MAX, (const unsigned char *)"123456789", 9) ^ UINT32_MAX)
        != UINT32_C(0xcbf43926)) {
        fputs("CRC-32 known-vector failure\n", stderr);
        return 1;
    }
    FILE *file = tmpfile();
    if (!file) {
        perror("tmpfile");
        return 1;
    }
    /* Fixed static storage also fits targets whose configured stack is <64 KiB. */
    static unsigned char buffer[BUFFER_SIZE];
    uint32_t checksums[2] = {0, 0};
    uint64_t read_calls = 0, write_calls = 0;
    int failed = 0;
    for (unsigned pass = 0; pass < 2 && !failed; ++pass) {
        uint32_t expected = UINT32_MAX, actual = UINT32_MAX;
        for (uint64_t offset = 0; offset < size;) {
            size_t count = (size_t)(size - offset < chunk ? size - offset : chunk);
            for (size_t i = 0; i < count; ++i) buffer[i] = pattern(offset + i, pass);
            expected = crc_update(expected, buffer, count);
            if (seek_file(file, offset) || fwrite(buffer, 1, count, file) != count) {
                fputs("mock write failed\n", stderr);
                failed = 1;
                break;
            }
            ++write_calls;
            offset += count;
        }
        if (inject && pass == 0 && !failed) {
            unsigned char byte;
            if (seek_file(file, corrupt_at) || fread(&byte, 1, 1, file) != 1) failed = 1;
            else {
                byte ^= 0x80u;
                if (seek_file(file, corrupt_at) || fwrite(&byte, 1, 1, file) != 1) failed = 1;
            }
            if (failed) fputs("corruption injection I/O failed\n", stderr);
        }
        for (uint64_t offset = 0; offset < size && !failed;) {
            size_t count = (size_t)(size - offset < chunk ? size - offset : chunk);
            if (seek_file(file, offset) || fread(buffer, 1, count, file) != count) {
                fputs("mock read failed\n", stderr);
                failed = 1;
                break;
            }
            ++read_calls;
            for (size_t i = 0; i < count; ++i) {
                if (buffer[i] != pattern(offset + i, pass)) {
                    fprintf(stderr, "mock mismatch: pass %u, byte %" PRIu64 "\n",
                            pass + 1, offset + i);
                    failed = 1;
                    break;
                }
            }
            actual = crc_update(actual, buffer, count);
            offset += count;
        }
        if (!failed && actual != expected) {
            fputs("mock CRC mismatch\n", stderr);
            failed = 1;
        }
        checksums[pass] = actual ^ UINT32_MAX;
    }
    if (fclose(file)) {
        fputs("mock close failed\n", stderr);
        failed = 1;
    }
    if (failed) return 1;
    printf("{\"backend\":\"host-file-mock\",\"mock\":true,"
           "\"physical_link_tested\":false,\"bytes_per_pass\":%" PRIu64 ","
           "\"bytes_verified\":%" PRIu64 ",\"verified_passes\":2,"
           "\"chunk\":%" PRIu64 ",\"working_buffer_bytes\":%u,"
           "\"crc32_pass1\":\"%08" PRIx32 "\",\"crc32_pass2\":\"%08" PRIx32 "\","
           "\"read_transfers\":%" PRIu64 ",\"write_transfers\":%" PRIu64 "}\n",
           size, 2 * size, chunk, BUFFER_SIZE, checksums[0], checksums[1], read_calls, write_calls);
    return 0;
}
