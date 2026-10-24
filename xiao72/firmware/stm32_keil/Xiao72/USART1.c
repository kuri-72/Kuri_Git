/**
 * USART1.c — 串口接收（USART1 / PA9=TX / PA10=RX / 115200 8N1）
 * ================================================================
 * 为什么用环形缓冲（FIFO）而不是单个变量？
 *
 *   115200 波特率下，17 字节一帧约需 1.5ms 发完。
 *   主循环里如果恰好正在刷 OLED（几 ms），一个字节变量会被后续字节覆盖 → 丢帧。
 *   64 字节 FIFO 能扛住整帧突发，这是嵌入式标准做法。
 *
 * 谁调用谁：
 *   中断  USART1_IRQHandler  → 写 FIFO
 *   主循环 x72_rx_take()      → 读 FIFO → 喂给 x72_feed()
 *
 * 单生产者（中断）+ 单消费者（主循环），不需要关中断保护：
 * head 只由中断写，tail 只由主循环写，8 位变量读写天然原子。
 */
#include "x72_port.h"

#define RX_MASK (X72_RX_BUF_SIZE - 1u)

static volatile uint8_t  s_head = 0;      /* 中断写 */
static volatile uint8_t  s_tail = 0;      /* 主循环写 */
static volatile uint8_t  s_buf[X72_RX_BUF_SIZE];
static volatile uint16_t s_count = 0;     /* 累计字节数 */
static volatile uint8_t  s_overflow = 0;  /* 发生过溢出 */

/* ================================================================
 *  初始化
 * ================================================================
 *  即使没插 USB-TTL 也可以调用：TX 引脚会往外发，但没人接，完全无害。
 *  RX 引脚配成上拉输入，悬空时不会收到乱码。
 */
void USART1_Init(uint32_t baud)
{
    GPIO_InitTypeDef  gpio;
    USART_InitTypeDef usart;
    NVIC_InitTypeDef  nvic;

    s_head = 0;
    s_tail = 0;
    s_count = 0;
    s_overflow = 0;

    RCC_APB2PeriphClockCmd(RCC_APB2Periph_USART1 | RCC_APB2Periph_GPIOA, ENABLE);

    /* PA9 = TX，复用推挽输出 */
    gpio.GPIO_Pin   = GPIO_Pin_9;
    gpio.GPIO_Mode  = GPIO_Mode_AF_PP;
    gpio.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_Init(GPIOA, &gpio);

    /* PA10 = RX，上拉输入 */
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

    /* TIM2 用抢占优先级 2，串口用 3（数值越大优先级越低） */
    nvic.NVIC_IRQChannel                   = USART1_IRQn;
    nvic.NVIC_IRQChannelPreemptionPriority = 3;
    nvic.NVIC_IRQChannelSubPriority        = 3;
    nvic.NVIC_IRQChannelCmd                = ENABLE;
    NVIC_Init(&nvic);
}

/* ================================================================
 *  中断：把字节塞进 FIFO
 * ================================================================
 *  这个函数放在这里而不是 stm32f10x_it.c，是为了"谁用谁管"。
 *  startup 文件里 USART1_IRQHandler 是 WEAK，这里定义会覆盖它，不会有重复定义。
 */
void USART1_IRQHandler(void)
{
    if (USART_GetITStatus(USART1, USART_IT_RXNE) != RESET) {
        uint8_t byte = (uint8_t)USART_ReceiveData(USART1);
        uint8_t next = (uint8_t)((s_head + 1u) & RX_MASK);

        if (next != s_tail) {           /* 还有空位 */
            s_buf[s_head] = byte;
            s_head = next;
        } else {
            s_overflow = 1;             /* 满了：丢掉这个字节并做标记 */
        }
        if (s_count < 0xFFFFu) s_count++;

        USART_ClearITPendingBit(USART1, USART_IT_RXNE);
    }
}

/* ================================================================
 *  主循环侧接口
 * ================================================================ */
uint8_t x72_rx_take(uint8_t *byte)
{
    if (s_tail == s_head) return 0;     /* 空 */
    *byte = s_buf[s_tail];
    s_tail = (uint8_t)((s_tail + 1u) & RX_MASK);
    return 1;
}

uint16_t x72_rx_count(void)
{
    return s_count;
}

uint8_t x72_rx_overflow(void)
{
    return s_overflow;
}
