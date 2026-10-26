#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Apply GPIO fix to locked reference patch and exercise actual callbacks in mock MMIO."""
import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile


def function(source, name):
    match = re.search(r"static (?:int|void) " + name + r"\(", source)
    if not match:
        raise ValueError(f"missing callback {name}")
    start = source.index("{", match.start())
    level = 1
    end = start + 1
    while level:
        level += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[match.start():end]


STUB = r'''
#undef NDEBUG
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define BIT(n) (UINT32_C(1) << (n))
#define GPIO_LINE_DIRECTION_OUT 0
#define GPIO_LINE_DIRECTION_IN 1
#define ENODEV 19
typedef uint32_t u32;
struct regs {unsigned out_w1ts,out_w1tc,enable_w1ts,enable_w1tc,pin_offset;};
struct esp32p4_gpio {unsigned char *base,*iomux; const struct regs *regs;};
struct gpio_chip {struct esp32p4_gpio *data;};
static struct esp32p4_gpio *gpiochip_get_data(struct gpio_chip *gc) {return gc->data;}
static unsigned char page[4096], mux[1024];
static unsigned addresses[8], count;
static u32 readl(void *p) {u32 v;memcpy(&v,p,4);return v;}
static void store(void *p,u32 v) {memcpy(p,&v,4);}
static void writel(u32 v,void *p) {
 uintptr_t a=(uintptr_t)p, b=(uintptr_t)page;
 assert(count<8); addresses[count++]=(unsigned)(a>=b && a<b+sizeof(page)?a-b:0x1000+a-(uintptr_t)mux);
 for(unsigned bank=0;bank<2;bank++) {
  unsigned out=bank?0x10:0x04,en=bank?0x2c:0x20;
  if(p==page+out+4) {store(page+out,readl(page+out)|v);return;}
  if(p==page+out+8) {store(page+out,readl(page+out)&~v);return;}
  if(p==page+en+4) {store(page+en,readl(page+en)|v);return;}
  if(p==page+en+8) {store(page+en,readl(page+en)&~v);return;}
 }
 store(p,v);
}
'''

MAIN = r'''
int main(void) {
 for(unsigned bank=0;bank<2;bank++) {
  struct regs r=bank?(struct regs){0x14,0x18,0x30,0x34,32}:(struct regs){0x08,0x0c,0x24,0x28,0};
  struct esp32p4_gpio g={page,mux,&r};struct gpio_chip gc={&g};
  unsigned en=r.enable_w1ts-4,out=r.out_w1ts-4;
  for(unsigned pin=0;pin<(bank?23:32);pin++) {
   uint32_t mask=BIT(pin),initial=UINT32_C(0xa5a55a5a);
   store(page+en,initial);store(page+out,~initial);count=0;
   assert(!esp32p4_gpio_direction_input(&gc,pin));
   assert(readl(page+en)==(initial&~mask));assert(readl(page+out)==~initial);assert(count==1);
   assert(esp32p4_gpio_get_direction(&gc,pin)==GPIO_LINE_DIRECTION_IN);
   for(int value=0;value<2;value++) {
    store(page+en,initial);store(page+out,~initial);count=0;
    assert(!esp32p4_gpio_direction_output(&gc,pin,value));
    assert(readl(page+en)==(initial|mask));assert(readl(page+out)==(value?(~initial|mask):(~initial&~mask)));
    assert(count==2);assert(addresses[0]==(value?r.out_w1ts:r.out_w1tc));assert(addresses[1]==r.enable_w1ts);
    assert(esp32p4_gpio_get_direction(&gc,pin)==GPIO_LINE_DIRECTION_OUT);
   }
   count=0;esp32p4_gpio_free(&gc,pin);assert(count==1);assert(readl(page+en)==(initial&~mask));
   unsigned global=r.pin_offset+pin,sel=0x558+global*4,io=4+global*4;
   store(page+en,initial|mask);
   store(page+sel,UINT32_C(0xfffffaff));store(mux+io,UINT32_C(0xdeadbeef));
   unsigned char before[4096],before_mux[1024];memcpy(before,page,sizeof page);memcpy(before_mux,mux,sizeof mux);count=0;
   assert(!esp32p4_gpio_request(&gc,pin));assert(count==3);assert(addresses[0]==r.enable_w1tc);
   assert(readl(page+sel)==((UINT32_C(0xfffffaff)&~UINT32_C(0xfff))|256|BIT(10)));
   assert((readl(mux+io)&(7u<<12))==(1u<<12));assert(readl(mux+io)&BIT(9));
   memcpy(before+sel,page+sel,4);memcpy(before_mux+io,mux+io,4);
   {uint32_t expected=(initial&~mask);memcpy(before+en,&expected,4);}
   assert(!memcmp(before,page,sizeof page));assert(!memcmp(before_mux,mux,sizeof mux));
  }
 }
 puts("GPIO mock MMIO: 55 lines, direction/latch/release/routing isolation PASS");return 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True, help="locked WHY2025 0002 patch")
    parser.add_argument("--cc", required=True)
    parser.add_argument("--zig", action="store_true")
    args = parser.parse_args()
    patch = Path(__file__).resolve().parents[1] / "linux/kernel-patches/0083-gpio-esp32p4-isolate-direction.patch"
    raw = args.reference.read_bytes()
    if hashlib.sha256(raw).hexdigest() != "c51e63afe2bbab043375eecd969cd6ce66951a6d72eb9ec0906f7c1a58ab7ae9":
        parser.error("reference does not match locked WHY2025 patch SHA-256")
    reference = raw.decode("utf8").split("+++ b/drivers/gpio/gpio-esp32p4.c", 1)[1]
    original = "\n".join(line[1:] for line in reference.splitlines() if line.startswith("+")) + "\n"
    with tempfile.TemporaryDirectory(prefix="gpio-kernel-mock-") as temporary:
        root = Path(temporary)
        driver = root / "drivers/gpio/gpio-esp32p4.c"
        driver.parent.mkdir(parents=True)
        driver.write_text(original, encoding="utf8", newline="\n")
        subprocess.run(["git", "apply", str(patch)], cwd=root, check=True)
        source = driver.read_text(encoding="utf8")
        config = source.split("struct gpio_generic_chip_config gcfg =", 1)[1].split("};", 1)[0]
        if re.search(r"\.dir(?:out|in)\s*=", config):
            raise ValueError("generic init still receives direction command registers")
        for text in ('"esp32p4-gpio-bank0"', '"esp32p4-gpio-bank1"', "bank_id ? 23 : ESP32P4_GPIO_NGPIO"):
            if text not in source:
                raise ValueError(f"missing identity/range fix: {text}")
        for name in ("direction_input", "direction_output", "get_direction", "free", "request"):
            if f"gpio->ggc.gc.{name} = esp32p4_gpio_{name};" not in source:
                raise ValueError(f"callback is not installed: {name}")
        macros = "\n".join(line for line in source.splitlines() if line.startswith("#define") and
                           any(line.split()[1].split("(")[0] == name for name in (
                               "ESP32P4_GPIO_FUNC_OUT_SEL", "ESP32P4_GPIO_OUT_SEL_MASK", "ESP32P4_GPIO_OUT_SEL_GPIO",
                               "ESP32P4_IO_MUX_PIN", "IO_MUX_MCU_SEL_MASK", "IO_MUX_MCU_SEL_GPIO", "IO_MUX_FUN_IE")))
        callbacks = "\n".join(function(source, "esp32p4_gpio_" + name) for name in
                              ("direction_input", "direction_output", "free", "get_direction", "request"))
        test = root / "test.c"
        test.write_text(STUB + macros + "\n" + callbacks + "\n" + MAIN, encoding="utf8")
        binary = root / "test.exe"
        subprocess.run([args.cc] + (["cc"] if args.zig else []) +
                       ["-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", str(test), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True, timeout=30)


if __name__ == "__main__":
    main()
