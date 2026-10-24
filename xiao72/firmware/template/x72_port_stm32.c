/**
 * x72_port_stm32.c — 平台适配层（标准库版）
 * ==========================================================================
 * 你只需要动这个文件，x72_proto.c 一个字都不要改。
 *
 * ★★★ 重要：不要整个文件直接加进工程 ★★★
 * 这个文件里的 SysTick_Handler 和 USART1_IRQHandler 通常和你的工程**冲突**
 * （重复定义 → 链接报错 multiple definition）。
 * 正确做法：把下面 3 个"必须实现"的函数复制到你已有的 .c 文件里；
 * 中断服务函数要么注释掉、要么把它们的内容合并进你已有的中断函数。
 *
 * 必须实现的 3 个函数：
 *   1) uint32_t x72_tick_ms(void)           毫秒计时
 *   2) void     x72_led_write(uint8_t)      亮度 → PWM
 *   3) void     x72_on_error(x72_status_t)  错误上报（可以空实现）
 */
#include "x72_proto.h"
#include "stm32f10x.h"

/* ================================================================
 *  1) 毫秒计时
 * ================================================================
 *  方案 A（推荐）：你的工程已有 1ms 计数变量，直接返回它。
 *     江科大 delay.c 里一般是 u16 g_ms; 或 u32 g_ms;
 *     注意：u16 会在 65 秒后溢出，如果拿去做呼吸相位会跳变，建议用 u32。
 *
 *  方案 B：没有现成变量 → 自己加一个，并在 SysTick_Handler 里自增。
 *     见文件末尾的"SysTick 可选片段"。
 */

/* --- 方案 A：如果你有现成的 ms 变量，取消下面注释并改名字 --- */
/*
extern uint32_t g_ms;          // ← 改成你工程里真实的变量名
uint32_t x72_tick_ms(void) { return g_ms; }
*/

/* --- 方案 B：自己维护一个（默认启用，最不容易出错） --- */
static volatile uint32_t s_ms = 0;

void x72_tick_inc(void)        /* ← 在 SysTick_Handler 里调用这一句即可 */
{
    s_ms++;
}

uint32_t x72_tick_ms(void)
{
    return s_ms;
}

/* ================================================================
 *  2) 亮度 → PWM
 * ================================================================
 *  你的 PWM_SetCompare1(x) 里 x 的范围取决于 PWM_Init 的 TIM_Period：
 *
 *    TIM_Period = 100   → 100 级，x 取 0..100      → X72_PWM_MAX = 100
 *    TIM_Period = 999   → 1000 级，x 取 0..999     → X72_PWM_MAX = 999
 *    TIM_Period = 99    → 100 级但最大 99          → X72_PWM_MAX = 99
 *
 *  ⚠ 先回去看一眼你 PWM_Init 里 TIM_Period 设了多少，再定这个值。
 *    设错的表现：灯永远到不了最亮，或者 50% 时就已经全亮。
 */
#define X72_PWM_MAX 100

void x72_led_write(uint8_t percent)
{
    uint16_t ccr;
    if (percent > 100u) percent = 100u;
    ccr = (uint16_t)((uint32_t)percent * X72_PWM_MAX / 100u);
    TIM_SetCompare1(TIM2, ccr);     /* ← 等价于你的 PWM_SetCompare1(ccr) */
}

/* ================================================================
 *  3) 错误上报（可选）
 * ================================================================
 *  第一版建议直接空实现，别在中断里做串口打印（容易卡死）。
 *  想调试时再打开：注意 x72_on_error 可能被中断调用，打印会阻塞。
 */
void x72_on_error(x72_status_t err)
{
    (void)err;      /* 第一版：什么都不做 */
}

/* ================================================================
 *  可选片段（不要同时启用，按你的工程情况二选一）
 * ================================================================ */

/* ---- 片段 1：你没有 SysTick_Handler，需要自己提供 ---- */
/*
void SysTick_Handler(void)
{
    x72_tick_inc();
}
*/

/* ---- 片段 2：你已经有 SysTick_Handler，在里面加一行 ---- */
/*
void SysTick_Handler(void)          // ← 你工程里原有的那个
{
    // ... 你原来的代码（比如 delay 的计数）...
    x72_tick_inc();                 // ← 只加这一行
}
*/

/* ================================================================
 *  USART1 接收（可选，阶段 3 才用）
 * ================================================================
 *  前提：USART1 已初始化（PA9=TX, PA10=RX, 115200, 8N1），并开了 RXNE 中断。
 *  下面这套用"单字节全局变量 + 主循环取走"，最简单、最不容易出竞态。
 *  比"在中断里直接解析"更安全，因为解析可能耗时，中断里不该做。
 */
volatile uint8_t  g_x72_rx_byte = 0;
volatile uint8_t  g_x72_rx_ready = 0;

void USART1_IRQHandler(void)
{
    if (USART_GetITStatus(USART1, USART_IT_RXNE) != RESET) {
        uint8_t b = (uint8_t)USART_ReceiveData(USART1);
        if (!g_x72_rx_ready) {          /* 上一字节没被取走就丢弃，防覆盖 */
            g_x72_rx_byte = b;
            g_x72_rx_ready = 1;
        }
        USART_ClearITPendingBit(USART1, USART_IT_RXNE);
    }
}

/* ================================================================
 *  USART1 初始化（可选，阶段 3 才用）
 * ================================================================
 *  ⚠ 如果你的工程里已经有 USART1_Init，不要用这个，改用你已有的。
 *  这个函数只做最小配置：115200 8N1，开接收中断。
 */
void x72_usart1_init(uint32_t baud)
{
    GPIO_InitTypeDef  gpio;
    USART_InitTypeDef usart;
    NVIC_InitTypeDef  nvic;

    RCC_APB2PeriphClockCmd(RCC_APB2Periph_USART1 | RCC_APB2Periph_GPIOA, ENABLE);

    /* PA9 = TX，复用推挽 */
    gpio.GPIO_Pin   = GPIO_Pin_9;
    gpio.GPIO_Mode  = GPIO_Mode_AF_PP;
    gpio.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_Init(GPIOA, &gpio);

    /* PA10 = RX，上拉输入（悬空时不会乱收） */
    gpio.GPIO_Pin  = GPIO_Pin_10;
    gpio.GPIO_Mode = GPIO_Mode_IPU;
    GPIO_Init(GPIOA, &gpio);

    usart.USART_BaudRate            = baud;
    usart.USART_WordLength          = USART_WordLength_8b;
    usart.USART_StopBits            = USART_StopBits_1;
    usart.USART_Parity              = USART_Parity_No;
    usart.USART_HardwareFlowControl = USART_HardwareFlowControl_None;
    usart.USART_Mode                = USART_Mode_Rx | USART_Mode_Tx;
    USART_Init(USART1, &usart);

    USART_ITConfig(USART1, USART_IT_RXNE, ENABLE);
    USART_Cmd(USART1, ENABLE);

    nvic.NVIC_IRQChannel                   = USART1_IRQn;
    nvic.NVIC_IRQChannelPreemptionPriority = 1;
    nvic.NVIC_IRQChannelSubPriority        = 1;
    nvic.NVIC_IRQChannelCmd                = ENABLE;
    NVIC_Init(&nvic);
}
