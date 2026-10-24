#include "stm32f10x.h"                  // Device header
#include "Delay.h"
#include "PWM.h"
#include "x72_proto.h"
#include "x72_port.h"
#include "x72_app.h"

#if X72_USE_KEY
#include "Key.h"
#endif

/* ================================================================
 *  小72 · 串口驱动的 LED 控制器
 * ================================================================
 *  数据流：
 *     PC/串口  →  USART1 中断  →  环形缓冲
 *              →  x72_feed(字节)  →  解析器
 *              →  x72_state {亮度, 周期}
 *              →  x72_effect_tick(ms)  →  呼吸/平滑
 *              →  PWM_SetCompare1()   →  PA0
 *
 *  支持两种输入格式（手敲都行）：
 *     [L00502000|A---|]            紧凑帧：亮度 50%，呼吸 2000ms
 *     {"led":50,"period":2000}     JSON：同上
 *
 *  ⚠ 没接 USB-TTL 时，串口部分不会有数据进来，但程序照常运行。
 *    想现在就看到灯动，把下面 "TEST INJECT" 那段注释打开。
 * ================================================================ */

/* ---- TEST INJECT：没有串口时用它验证解析器 ---- */
/* 打开下面这行，上电 1 秒后会自己发一帧进来 */
/* #define X72_SELF_TEST */

int main(void)
{
    uint8_t rx_byte;

    /* ---------------- 模块初始化 ---------------- */
    Delay_ms(100);              /* 等电源稳定（你原来没有，加上更稳） */
    PWM_Init();                 /* PA0 PWM + 开启 TIM2 1ms 中断 */
    USART1_Init(X72_UART_BAUD); /* PA9/PA10，没接模块也无害 */
#if X72_USE_OLED
    x72_app_disp_init();        /* OLED：PB8/PB9 */
#endif

    /* ================================================================
     *  【预留：按键初始化】
     *  回家测按键时，把 x72_port.h 里 X72_USE_KEY 改成 1，
     *  这里会自动编进来。
     * ================================================================ */
#if X72_USE_KEY
    Key_Init();
#endif

    /* ================================================================
     *  【预留：你自己的测试入口】
     *  想绕过串口直接喂一帧，把 X72_SELF_TEST 打开，
     *  或直接在这里写一行：
     *
     *      x72_parse_line("[L01002000|A---|]");
     *      x72_parse_line("{\"led\":50,\"period\":1000}");
     *
     *  常见组合：
     *      [L00500000|A---|]   50% 常亮
     *      [L01002000|A---|]   100% 呼吸 2 秒
     *      [L00301000|A---|]   30% 呼吸 1 秒
     *      {"led":80}          只改亮度，周期不变
     *      {"period":500}      只改周期，亮度不变
     * ================================================================ */
x72_parse_line("[L01002000|A---|]");
#ifdef X72_SELF_TEST
    /* 重复注入：哪一行想试就取消注释（默认周期 3 秒） */
    #define X72_TEST_FRAME  "[L01002000|A---|]"
    static uint32_t s_next_test = 1000u;
    static uint8_t  s_test_done = 0;
#endif

    /* ---------------- 主循环 ---------------- */
    while (1)
    {
        /* 1) 串口字节 → 解析器（没有数据时立即返回，不阻塞） */
        while (x72_rx_take(&rx_byte))
        {
            x72_feed(rx_byte);
        }

#ifdef X72_SELF_TEST
        /* 2) 自测注入：用于没有串口时验证 */
        {
            uint32_t now = x72_tick_ms();
            if (!s_test_done && now >= s_next_test)
            {
                s_test_done = 1;
                x72_parse_line(X72_TEST_FRAME);
            }
        }
#endif

        /* 3) 呼吸 + 平滑（非阻塞，每 1ms 推进一次） */
        x72_effect_tick(x72_tick_ms());

        /* 4) OLED 刷新（内部限速 200ms） */
#if X72_USE_OLED
        x72_app_disp_tick(x72_tick_ms());
#endif

        /* ================================================================
         *  【预留：按键处理】
         *  注意 Key_GetNum() 是阻塞的（按住不放会卡住），
         *  所以只在检测到按下时调用，别每圈都调。
         *
         *  示例：
         *      if (Key_GetNum() == 1) {
         *          uint8_t b = x72_state.brightness + 20;
         *          if (b > 100) b = 100;
         *          x72_state.brightness = b;
         *          x72_state.dirty = 1;
         *      }
         * ================================================================ */
#if X72_USE_KEY
        {
            uint8_t key = Key_GetNum();
            if (key == 1) {          /* 按键1：亮度 +20% */
                uint8_t b = x72_state.brightness;
                b = (uint8_t)((b > 80) ? 100 : (b + 20));
                x72_state.brightness = b;
                x72_state.period_ms = 0;    /* 按一下退出呼吸，变成常亮 */
                x72_state.valid = 1;
                x72_state.dirty = 1;
            } else if (key == 2) {   /* 按键2：呼吸开关 */
                x72_state.period_ms = x72_state.period_ms ? 0 : 2000;
                x72_state.valid = 1;
                x72_state.dirty = 1;
            }
        }
#endif

        /* 主循环不需要额外延时：x72_effect_tick 靠 millis 推算，
           空转也不会让呼吸变快或变慢。加个空操作也行。 */
    }
}
