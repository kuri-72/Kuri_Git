/**
 * x72_app.c — OLED 状态显示（本工程专属）
 * =========================================
 * 屏幕布局（16x16 字体，一屏 4 行，每行**最多 16 字符**）：
 *
 *     Line1:  X72 RUNNING          ← 运行状态（11 字符）
 *     Line2:  BRI:100%  F:01       ← 输出亮度 / 成功帧数（14 字符）
 *     Line3:  PER:2000ms           ← 呼吸周期（11 字符）
 *     Line4:  RX:0000   E:00       ← 累计字节 / 失败帧数（14 字符）
 *
 * ⚠ 列数上限的坑（v0.1 踩过）：
 *     OLED_ShowChar 的坐标是 (Column-1)*8。Column=17 时 X=128，
 *     超出 0~127，SSD1306 会把列地址回卷到最左边，
 *     导致第 17 个字符覆盖第 1 列（表现为首字符闪烁）。
 *     所以这里每行都严格 ≤16 字符，并且末尾再做一次兜底截断。
 *
 * 只调用 OLED.h 里的公开函数，不碰底层时序。
 * 刷新限速 200ms：软件 I2C 刷太快会占主循环时间，而且数字看不清。
 */
#include "x72_app.h"

#if X72_USE_OLED

#include "OLED.h"
#include "x72_proto.h"

#define LINE_CHARS 16u

static uint32_t s_next_refresh = 0;

/* 把 buf 的前 16 字符填成空格，并保证 [16] = '\0' */
static void line_clear(char *buf)
{
    uint8_t i;
    for (i = 0; i < LINE_CHARS; i++) buf[i] = ' ';
    buf[LINE_CHARS] = '\0';
}

/**
 * 把 value 按固定宽度右对齐补零写进 buf[pos..pos+width-1]
 * 返回下一个可用下标；越界时钳到 16，防止写穿。
 */
static uint8_t put_num(char *buf, uint8_t pos, uint32_t value, uint8_t width)
{
    uint8_t i;
    if ((uint16_t)pos + width > LINE_CHARS) return LINE_CHARS;
    for (i = 0; i < width; i++) {
        buf[pos + (uint8_t)(width - 1u - i)] = (char)('0' + (value % 10u));
        value /= 10u;
    }
    return (uint8_t)(pos + width);
}

/**
 * 兜底：确保字符串不超过 16 字符。
 * 比"指望每次都能数对"可靠 —— v0.1 就是数错了一格。
 */
static void line_guard(char *buf)
{
    uint8_t i;
    for (i = 0; i <= LINE_CHARS; i++) {
        if (buf[i] == '\0') return;      /* 已找到结尾，够短 */
    }
    buf[LINE_CHARS] = '\0';              /* 超长则硬截断 */
}

void x72_app_disp_init(void)
{
    OLED_Init();
    OLED_Clear();
    OLED_ShowString(1, 1, (char *)"X72 BOOT");
    s_next_refresh = 0;
}

void x72_app_disp_tick(uint32_t now_ms)
{
    char line[LINE_CHARS + 1];
    uint8_t p, i;

    /* 限速：未到时间直接返回 */
    if ((int32_t)(now_ms - s_next_refresh) < 0) return;
    s_next_refresh = now_ms + 200u;      /* 5Hz */

    /* ---------- Line1：X72 RUNNING (11) ---------- */
    line_clear(line);
    {
        const char *st = x72_state.valid ? "X72 RUNNING" : "X72 WAITING";
        for (i = 0; st[i] != '\0' && i < LINE_CHARS; i++) line[i] = st[i];
    }
    line_guard(line);
    OLED_ShowString(1, 1, line);

    /* ---------- Line2：BRI:100%  F:01 (14) ---------- */
    line_clear(line);
    line[0] = 'B'; line[1] = 'R'; line[2] = 'I'; line[3] = ':';
    /* 内部刻度 0..1000，显示用 0..100 */
    p = put_num(line, 4, x72_effect_brightness() / 10u, 3);   /* 4..6 */
    line[p++] = '%';                                    /* 7     */
    line[p++] = ' ';                                    /* 8     */
    line[p++] = 'F';                                    /* 9     */
    line[p++] = ':';                                    /* 10    */
    p = put_num(line, p, x72_frames_ok, 2);             /* 11..12*/
    line_guard(line);
    OLED_ShowString(2, 1, line);

    /* ---------- Line3：PER:2000ms (11) ---------- */
    line_clear(line);
    line[0] = 'P'; line[1] = 'E'; line[2] = 'R'; line[3] = ':';
    p = put_num(line, 4, x72_state.period_ms, 4);       /* 4..7 */
    line[p++] = 'm'; line[p++] = 's';                   /* 8,9  */
    line_guard(line);
    OLED_ShowString(3, 1, line);

    /* ---------- Line4：RX:0000   E:00 (14) ---------- */
    line_clear(line);
    line[0] = 'R'; line[1] = 'X'; line[2] = ':';
    p = put_num(line, 3, x72_rx_count(), 4);            /* 3..6 */
    p++;                                                /* 7 留空 */
    line[p++] = 'E';                                    /* 8 */
    line[p++] = ':';                                    /* 9 */
    p = put_num(line, p, x72_frames_err, 2);            /* 10..11 */
    line_guard(line);
    OLED_ShowString(4, 1, line);

    /* 溢出标记：发生过丢字节时在右下角打感叹号（第 16 列） */
    if (x72_rx_overflow()) {
        OLED_ShowChar(4, 16, '!');
    }
}

#endif /* X72_USE_OLED */
