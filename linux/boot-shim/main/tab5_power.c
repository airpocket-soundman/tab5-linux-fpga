// SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-only
/*
 * M5Stack Tab5: switch the ESP32-C6 supply on before SDIO bring-up.
 *
 * On the Tab5 the C6 is not powered from the P4 rail.  Its 3.3 V comes from
 * an LPW5209 load switch whose EN is WLAN_PWR_EN, output P0 of the
 * PI4IOE5V6408 at I2C address 0x44 (ADDR tied high).  A second expander at
 * 0x43 (ADDR low) drives RF_PTH_L_INT_H_EXT on P0, the C6 antenna switch:
 * low selects the internal antenna.  Both sit on the system I2C bus
 * (SDA GPIO31, SCL GPIO32, 2.2 k pull-ups) and are reset with CHIP_PU, so
 * every cold boot starts with the C6 unpowered.
 *
 * The same 0x43 expander drives LCD_RST on P4 (high = panel running), and
 * GPIO22 enables the backlight boost converter; Linux has drivers for
 * neither, so tab5_lcd_power_on() sets both before the handoff.
 * The opt-in USB host path also enables USB-A VBUS on expander 0x44 P3.
 *
 * Nothing else here needs I2C, so the bus is bit-banged with open-drain GPIO
 * instead of pulling in the I2C driver; it is released (inputs) on return so
 * Linux and later drivers find the pins idle.  Only the expander bits named
 * above are changed; every other pin keeps its reset state.
 */

#include <stdbool.h>
#include <stdint.h>

#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_rom_sys.h"

#include "tab5_power.h"

#ifdef EASYSTICK_TAB5_MICROSD_SPI
#include "esp_ldo_regulator.h"

/* Keep the regulator acquired across the Linux handoff; do not release it. */
static esp_ldo_channel_handle_t tab5_sd_ldo;
#endif

static const char *TAG = "tab5-power";

#define TAB5_I2C_SDA GPIO_NUM_31
#define TAB5_I2C_SCL GPIO_NUM_32
#define I2C_HALF_PERIOD_US 5u /* about 100 kHz */

#define PI4IO_ADDR_SYS 0x43u  /* LCD/touch/camera resets, RF switch */
#define PI4IO_ADDR_PWR 0x44u  /* WLAN power, USB-A 5 V, charger */

#define PI4IO_REG_DEVICE_ID 0x01u
#define PI4IO_REG_IO_DIR 0x03u     /* 1 = output */
#define PI4IO_REG_OUT 0x05u
#define PI4IO_REG_OUT_HIGHZ 0x07u  /* 1 = output disabled (reset 0xff) */

#define PI4IO_PWR_WLAN_PWR_EN (1u << 0)
#define PI4IO_PWR_USB_EN (1u << 3)
#define PI4IO_SYS_RF_PTH_EXT (1u << 0)
#define PI4IO_SYS_LCD_RST (1u << 4)

#define TAB5_LCD_BACKLIGHT GPIO_NUM_22
#define LCD_RESET_ASSERT_US 10000u
#define LCD_RESET_READY_US 120000u

/* Settle time after the load switch turns on, before the reset sequence. */
#define C6_POWER_SETTLE_US 50000u

static void line_release(gpio_num_t pin)
{
	gpio_set_level(pin, 1);
}

static void line_low(gpio_num_t pin)
{
	gpio_set_level(pin, 0);
}

static void i2c_delay(void)
{
	esp_rom_delay_us(I2C_HALF_PERIOD_US);
}

static void i2c_start(void)
{
	line_release(TAB5_I2C_SDA);
	line_release(TAB5_I2C_SCL);
	i2c_delay();
	line_low(TAB5_I2C_SDA);
	i2c_delay();
	line_low(TAB5_I2C_SCL);
	i2c_delay();
}

static void i2c_stop(void)
{
	line_low(TAB5_I2C_SDA);
	i2c_delay();
	line_release(TAB5_I2C_SCL);
	i2c_delay();
	line_release(TAB5_I2C_SDA);
	i2c_delay();
}

static bool i2c_write_byte(uint8_t value)
{
	for (int bit = 7; bit >= 0; --bit) {
		if (value & (1u << bit))
			line_release(TAB5_I2C_SDA);
		else
			line_low(TAB5_I2C_SDA);
		i2c_delay();
		line_release(TAB5_I2C_SCL);
		i2c_delay();
		line_low(TAB5_I2C_SCL);
	}
	line_release(TAB5_I2C_SDA);
	i2c_delay();
	line_release(TAB5_I2C_SCL);
	i2c_delay();
	bool ack = gpio_get_level(TAB5_I2C_SDA) == 0;
	line_low(TAB5_I2C_SCL);
	i2c_delay();
	return ack;
}

static uint8_t i2c_read_byte_nack(void)
{
	uint8_t value = 0;

	line_release(TAB5_I2C_SDA);
	for (int bit = 7; bit >= 0; --bit) {
		i2c_delay();
		line_release(TAB5_I2C_SCL);
		i2c_delay();
		if (gpio_get_level(TAB5_I2C_SDA))
			value |= 1u << bit;
		line_low(TAB5_I2C_SCL);
	}
	/* NACK: leave SDA released for the ninth clock. */
	i2c_delay();
	line_release(TAB5_I2C_SCL);
	i2c_delay();
	line_low(TAB5_I2C_SCL);
	i2c_delay();
	return value;
}

static bool pi4io_read(uint8_t addr, uint8_t reg, uint8_t *value)
{
	bool ok;

	i2c_start();
	ok = i2c_write_byte(addr << 1) && i2c_write_byte(reg);
	if (ok) {
		i2c_start(); /* repeated start */
		ok = i2c_write_byte((addr << 1) | 1u);
		if (ok)
			*value = i2c_read_byte_nack();
	}
	i2c_stop();
	return ok;
}

static bool pi4io_write(uint8_t addr, uint8_t reg, uint8_t value)
{
	bool ok;

	i2c_start();
	ok = i2c_write_byte(addr << 1) && i2c_write_byte(reg) &&
	     i2c_write_byte(value);
	i2c_stop();
	return ok;
}

/* Drive the given expander pins as outputs at the given level. */
static bool pi4io_drive(uint8_t addr, uint8_t mask, bool high)
{
	uint8_t out, highz, dir;

	if (!pi4io_read(addr, PI4IO_REG_OUT, &out) ||
	    !pi4io_read(addr, PI4IO_REG_OUT_HIGHZ, &highz) ||
	    !pi4io_read(addr, PI4IO_REG_IO_DIR, &dir))
		return false;
	out = high ? (out | mask) : (out & ~mask);
	/* Level first, then enable the driver, so the pin never glitches. */
	return pi4io_write(addr, PI4IO_REG_OUT, out) &&
	       pi4io_write(addr, PI4IO_REG_OUT_HIGHZ, highz & ~mask) &&
	       pi4io_write(addr, PI4IO_REG_IO_DIR, dir | mask);
}

static void i2c_bus_claim(void)
{
	const gpio_config_t cfg = {
		.pin_bit_mask = (1ull << TAB5_I2C_SDA) | (1ull << TAB5_I2C_SCL),
		.mode = GPIO_MODE_INPUT_OUTPUT_OD,
		.pull_up_en = GPIO_PULLUP_ENABLE,
		.pull_down_en = GPIO_PULLDOWN_DISABLE,
		.intr_type = GPIO_INTR_DISABLE,
	};

	gpio_set_level(TAB5_I2C_SDA, 1);
	gpio_set_level(TAB5_I2C_SCL, 1);
	gpio_config(&cfg);
	/* Clock out a device that may hold SDA from an interrupted transfer. */
	for (int i = 0; i < 9 && gpio_get_level(TAB5_I2C_SDA) == 0; ++i) {
		line_low(TAB5_I2C_SCL);
		i2c_delay();
		line_release(TAB5_I2C_SCL);
		i2c_delay();
	}
	i2c_stop();
}

static void i2c_bus_release(void)
{
	gpio_set_direction(TAB5_I2C_SDA, GPIO_MODE_INPUT);
	gpio_set_direction(TAB5_I2C_SCL, GPIO_MODE_INPUT);
}

bool tab5_c6_power_on(void)
{
	uint8_t id = 0;
	bool ok;

	i2c_bus_claim();
	ok = pi4io_read(PI4IO_ADDR_PWR, PI4IO_REG_DEVICE_ID, &id);
	if (!ok) {
		ESP_LOGE(TAG, "no PI4IOE5V6408 at 0x%02x; C6 stays unpowered",
			 PI4IO_ADDR_PWR);
		i2c_bus_release();
		return false;
	}
	if (!pi4io_drive(PI4IO_ADDR_SYS, PI4IO_SYS_RF_PTH_EXT, false))
		ESP_LOGW(TAG, "antenna switch at 0x%02x not set; keeping its default",
			 PI4IO_ADDR_SYS);
	ok = pi4io_drive(PI4IO_ADDR_PWR, PI4IO_PWR_WLAN_PWR_EN, true);
	i2c_bus_release();
	if (!ok) {
		ESP_LOGE(TAG, "WLAN_PWR_EN write failed; C6 stays unpowered");
		return false;
	}
	esp_rom_delay_us(C6_POWER_SETTLE_US);
	ESP_LOGI(TAG, "C6 power on (expander 0x%02x id 0x%02x, WLAN_PWR_EN)",
		 PI4IO_ADDR_PWR, id);
	return true;
}

bool tab5_lcd_power_on(void)
{
	bool ok;

	i2c_bus_claim();
	ok = pi4io_drive(PI4IO_ADDR_SYS, PI4IO_SYS_LCD_RST, false);
	esp_rom_delay_us(LCD_RESET_ASSERT_US);
	ok = ok && pi4io_drive(PI4IO_ADDR_SYS, PI4IO_SYS_LCD_RST, true);
	i2c_bus_release();
	if (!ok) {
		ESP_LOGE(TAG, "LCD_RST write failed; the panel stays in reset");
		return false;
	}
	esp_rom_delay_us(LCD_RESET_READY_US);

	/* Linux keeps no GPIO22 state; leave the boost converter on. */
	gpio_reset_pin(TAB5_LCD_BACKLIGHT);
	gpio_set_direction(TAB5_LCD_BACKLIGHT, GPIO_MODE_OUTPUT);
	gpio_set_level(TAB5_LCD_BACKLIGHT, 1);
	ESP_LOGI(TAG, "LCD reset released (expander 0x%02x P4), backlight on",
		 PI4IO_ADDR_SYS);
	return true;
}

bool tab5_usb_host_power_on(void)
{
	i2c_bus_claim();
	bool ok = pi4io_drive(PI4IO_ADDR_PWR, PI4IO_PWR_USB_EN, true);
	i2c_bus_release();
	if (!ok) {
		ESP_LOGE(TAG, "USB_EN write failed; skipping USB host PHY init");
		return false;
	}
	ESP_LOGI(TAG, "USB-A VBUS enabled (expander 0x%02x P3)",
		 PI4IO_ADDR_PWR);
	return true;
}

#ifdef EASYSTICK_TAB5_MICROSD_SPI
bool tab5_microsd_spi_prepare(void)
{
	/* Tab5 BSP: CLK43, CMD/MOSI44, DAT0/MISO39, DAT3/CS42. */
	const gpio_num_t pins[] = {
		GPIO_NUM_43, GPIO_NUM_44, GPIO_NUM_39, GPIO_NUM_42,
	};
	for (unsigned i = 0; i < sizeof(pins) / sizeof(pins[0]); ++i) {
		if (gpio_reset_pin(pins[i]) != ESP_OK) {
			ESP_LOGE(TAG, "microSD GPIO reset failed");
			return false;
		}
		/* Preload safe latches without enabling an output. Linux owns SPI. */
		gpio_set_level(pins[i], pins[i] == GPIO_NUM_43 ? 0 : 1);
	}
	const gpio_config_t cfg = {
		.pin_bit_mask = (1ull << 43) | (1ull << 44) |
				(1ull << 39) | (1ull << 42),
		.mode = GPIO_MODE_INPUT,
		.pull_up_en = GPIO_PULLUP_ENABLE,
		.pull_down_en = GPIO_PULLDOWN_DISABLE,
		.intr_type = GPIO_INTR_DISABLE,
	};
	/* gpio_config selects PIN_FUNC_GPIO, disconnecting SDMMC IOMUX. */
	if (gpio_config(&cfg) != ESP_OK) {
		ESP_LOGE(TAG, "microSD GPIO input configuration failed");
		return false;
	}
	/* Idle CS/CMD high; idle clock low. No command or clock is sent here. */
	gpio_pullup_dis(GPIO_NUM_43);
	gpio_pulldown_en(GPIO_NUM_43);
	const esp_ldo_channel_config_t ldo = {
		.chan_id = 4,
		.voltage_mv = 3300,
	};
	esp_err_t err = esp_ldo_acquire_channel(&ldo, &tab5_sd_ldo);
	if (err != ESP_OK) {
		ESP_LOGE(TAG, "microSD LDO4 acquisition failed: %s", esp_err_to_name(err));
		return false;
	}
	esp_rom_delay_us(10000);
	ESP_LOGI(TAG, "microSD SPI prepared: LDO4=3300mV, GPIO43/44/39/42 inputs");
	return true;
}
#endif
