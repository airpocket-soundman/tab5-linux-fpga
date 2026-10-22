// SPDX-License-Identifier: Apache-2.0
#include <stdint.h>
#include "bsp/display.h"
#include "esp_check.h"
#include "esp_heap_caps.h"
#include "esp_lcd_panel_ops.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static esp_lcd_panel_handle_t panel;
static uint16_t *strip;

static void fill(int x, int y, int width, int height, uint16_t color)
{
    for (int i = 0; i < width * 20; ++i) strip[i] = color;
    for (int row = 0; row < height; row += 20) {
        int rows = height - row < 20 ? height - row : 20;
        ESP_ERROR_CHECK(esp_lcd_panel_draw_bitmap(panel, x, y + row, x + width, y + row + rows, strip));
    }
}

void app_main(void)
{
    ESP_LOGI("display-test", "Standalone display test: no Linux, Wi-Fi or FPGA traffic");
    bsp_display_config_t cfg = {
        .dsi_bus = {
            .phy_clk_src = MIPI_DSI_PHY_CLK_SRC_DEFAULT,
            .lane_bit_rate_mbps = BSP_LCD_MIPI_DSI_LANE_BITRATE_MBPS,
        },
    };
    esp_lcd_panel_io_handle_t io;
    ESP_ERROR_CHECK(bsp_display_new(&cfg, &panel, &io));
    strip = heap_caps_malloc(BSP_LCD_H_RES * 20 * sizeof(uint16_t), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    ESP_ERROR_CHECK(strip ? ESP_OK : ESP_ERR_NO_MEM);
    ESP_ERROR_CHECK(esp_lcd_panel_disp_on_off(panel, true));
    fill(0, 0, 720, 1280, 0x0000);
    fill(0, 0, 240, 320, 0xf800);
    fill(240, 0, 240, 320, 0x07e0);
    fill(480, 0, 240, 320, 0x001f);
    fill(0, 960, 720, 160, 0xffff);
    ESP_ERROR_CHECK(bsp_display_brightness_set(30));
    int x = 0, direction = 1;
    unsigned frame = 0;
    for (;;) {
        fill(x, 560, 100, 100, 0x0000);
        x += direction * 20;
        if (x >= 620) { x = 620; direction = -1; }
        if (x <= 0) { x = 0; direction = 1; }
        fill(x, 560, 100, 100, 0xffe0);
        fill(300, 760, 120, 80, (frame / 4) % 2 ? 0xffff : 0x001f);
        if (frame % 40 == 0) ESP_LOGI("display-test", "Animation alive, frame=%u", frame);
        ++frame;
        vTaskDelay(pdMS_TO_TICKS(125));
    }
}
