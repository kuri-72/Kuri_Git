/**
 * x72_proto.c — 协议解析 + 非阻塞呼吸（平台无关）
 * ==================================================
 * 支持两种输入，按首字符分派：
 *     '['  → 紧凑帧   [L00502000|A---|]
 *     '{'  → JSON     {"led":50,"period":2000}
 *
 * 亮度有两套刻度，别搞混：
 *   协议刻度  0..100   对外沿用（"亮度 50%"），4 位数字
 *   内部刻度  0..1000  呼吸/平滑都在这个刻度上算，PWM 也按它输出
 *   换算      internal = protocol * 10
 *
 * 为什么内部要 10 倍：100 级时呼吸每步跨 1%，慢呼吸能看出台阶。
 * 1000 级后每步 0.1%，PWM 侧同步提到 1000 级（见 x72_port.h）。
 *
 * 不用 sscanf/sprintf：Flash 小、栈开销可控、行为确定。
 */
#include "x72_proto.h"
#include <string.h>

/* ---------------- 平台钩子 ---------------- */
#ifdef X72_NO_PORT
/* PC 模拟器：这几个钩子由 sim_main.c 实现，这里只提供计时 */
static uint32_t s_sim_tick = 0;
uint32_t x72_tick_ms(void) { return s_sim_tick; }
void x72_sim_set_tick(uint32_t t) { s_sim_tick = t; }
/* 提醒：x72_led_write / x72_on_error 必须由模拟器提供，否则链接失败 */
#endif

/* ---------------- 刻度宏 ---------------- */
#define X72_BRIGHT_MIN_IN   0
#define X72_BRIGHT_MAX_IN   1000            /* 内部刻度上限 */
#define X72_BRIGHT_FROM_OUT(p)  ((p) * 10)  /* 0..100  → 0..1000 */
#define X72_BRIGHT_TO_OUT(i)    ((i) / 10)  /* 0..1000 → 0..100  */

/* ---------------- 静态缓冲 ---------------- */
#define X72_BUF_SIZE 48      /* 48 够放下最长的 JSON */

static char    s_buf[X72_BUF_SIZE];
static uint8_t s_len;

volatile x72_state_t x72_state = {0, 0, 0, 0};
volatile uint16_t    x72_frames_ok = 0;
volatile uint16_t    x72_frames_err = 0;

/* ---------------- 效果内部状态 ---------------- */
static uint32_t s_breath_t0;
static uint16_t s_breath_period;
static uint16_t s_bright_target;     /* 内部刻度 0..1000 */
static uint16_t s_bright_now;        /* 内部刻度 0..1000 */
static uint16_t s_last_pwm = 0xFFFF;

/* ---------------- 小工具 ---------------- */
static int is_digit(char c) { return c >= '0' && c <= '9'; }

/* 提交一帧新状态（两种格式共用，输入是**协议刻度** 0..100） */
static void apply_state(uint16_t led_out, uint16_t period)
{
    if (led_out > 100u)  led_out = 100u;      /* 限幅，不拒收 */
    if (period > 9999u)  period = 9999u;

    x72_state.brightness = (uint16_t)X72_BRIGHT_FROM_OUT(led_out);
    x72_state.period_ms  = (uint16_t)period;
    x72_state.valid      = 1;
    x72_state.dirty      = 1;
    x72_frames_ok++;
}

/* ================================================================
 *  A) 紧凑帧解析
 * ================================================================ */
static x72_status_t parse_frame(const char *buf, uint16_t len)
{
    const char *lb, *rb, *pa, *pb, *p, *q;
    uint16_t blen;
    uint16_t led, period;
    uint8_t i;

    lb = (const char *)memchr(buf, '[', (size_t)len);
    if (lb == NULL) return X72_E_FRAME;
    rb = (const char *)memchr(lb, ']', (size_t)(buf + len - lb));
    if (rb == NULL) rb = buf + len;          /* 无帧尾：宽容接受 */
    if (rb <= lb) return X72_E_FRAME;

    p = lb + 1;
    q = (const char *)memchr(p, '|', (size_t)(rb - p));
    if (q == NULL) return X72_E_FRAME;
    blen = (uint16_t)(q - p);

    /* 灯段必须正好 'L' + 8 位数字 */
    if (blen != 9) return X72_E_FRAME;
    if (p[0] != 'L') return X72_E_FRAME;
    for (i = 1; i <= 8; i++) {
        if (!is_digit(p[i])) return X72_E_FRAME;
    }

    led    = (uint16_t)((p[1]-'0')*1000 + (p[2]-'0')*100 + (p[3]-'0')*10 + (p[4]-'0'));
    period = (uint16_t)((p[5]-'0')*1000 + (p[6]-'0')*100 + (p[7]-'0')*10 + (p[8]-'0'));

    /* 第二段：机械臂占位，本版只校验首字母 */
    pa = q + 1;
    pb = (const char *)memchr(pa, '|', (size_t)(rb - pa));
    if (pb == NULL) pb = rb;
    if (pb > pa && pa[0] != 'A') return X72_E_FRAME;

    apply_state(led, period);
    return X72_OK;
}

/* ================================================================
 *  B) JSON 解析（手敲调试用，容错优先）
 * ================================================================ */
static int json_key_is(const char *body, uint16_t start, uint16_t klen,
                       const char *want)
{
    uint16_t j;
    size_t wl = strlen(want);
    if ((size_t)klen != wl) return 0;
    for (j = 0; j < klen; j++) {
        char a = body[start + j];
        char b = want[j];
        if (a >= 'A' && a <= 'Z') a = (char)(a - 'A' + 'a');
        if (a != b) return 0;
    }
    return 1;
}

static x72_status_t parse_json(const char *buf, uint16_t len)
{
    const char *lb = (const char *)memchr(buf, '{', (size_t)len);
    const char *rb = (const char *)memchr(buf, '}', (size_t)len);
    const char *body;
    uint16_t blen, i;
    int have_led = 0, have_period = 0;
    uint16_t led = 0, period = 0;

    if (lb == NULL || rb == NULL || rb <= lb) return X72_E_FRAME;
    body = lb + 1;
    blen = (uint16_t)(rb - body);

    i = 0;
    while (i < blen) {
        char c = body[i];
        if (c != '"') { i++; continue; }

        {
            uint16_t kstart = (uint16_t)(++i);
            uint16_t klen = 0;
            while (i < blen && body[i] != '"') { i++; klen++; }
            if (i >= blen) return X72_E_FRAME;      /* 引号没闭合 */
            i++;                                    /* 跳过结束引号 */

            while (i < blen && body[i] != ':') i++;
            if (i >= blen) return X72_E_FRAME;
            i++;                                    /* 跳过冒号 */
            while (i < blen && (body[i] == ' ' || body[i] == '\t')) i++;

            {
                uint32_t val = 0;
                int neg = 0, nd = 0;
                if (i < blen && body[i] == '-') { neg = 1; i++; }
                while (i < blen && is_digit(body[i])) {
                    val = val * 10u + (uint32_t)(body[i] - '0');
                    if (val > 100000u) val = 100000u;
                    i++; nd++;
                }
                if (neg) val = 0;           /* 负数按 0（限幅语义） */
                if (nd == 0) return X72_E_FRAME;

                if (json_key_is(body, kstart, klen, "led")) {
                    led = (uint16_t)(val > 0xFFFFu ? 0xFFFFu : val);
                    have_led = 1;
                } else if (json_key_is(body, kstart, klen, "period")) {
                    period = (uint16_t)(val > 0xFFFFu ? 0xFFFFu : val);
                    have_period = 1;
                }
                /* 未知键忽略，为将来扩展留口子 */
            }
        }
    }

    if (!have_led && !have_period) return X72_E_FRAME;

    /* 缺字段 = 保持不变（注意要转回协议刻度） */
    if (!have_led)    led = X72_BRIGHT_TO_OUT(x72_state.brightness);
    if (!have_period) period = x72_state.period_ms;

    apply_state(led, period);
    return X72_OK;
}

/* ================================================================
 *  统一入口
 * ================================================================ */
static x72_status_t dispatch_line(const char *buf, uint16_t len)
{
    uint16_t i;
    x72_status_t st;

    for (i = 0; i < len; i++) {
        if (buf[i] == '[') {
            st = parse_frame(buf, len);
            if (st != X72_OK) { x72_frames_err++; x72_on_error(st); }
            return st;
        }
        if (buf[i] == '{') {
            st = parse_json(buf, len);
            if (st != X72_OK) { x72_frames_err++; x72_on_error(st); }
            return st;
        }
    }
    x72_frames_err++;
    return X72_E_FRAME;         /* 两种格式都不像 */
}

void x72_reset(void)
{
    s_len = 0;
}

x72_status_t x72_parse_line(const char *line)
{
    size_t n;
    if (line == NULL) return X72_E_FRAME;
    n = strlen(line);
    if (n == 0) return X72_E_FRAME;
    if (n >= X72_BUF_SIZE) { x72_frames_err++; return X72_E_OVERFLOW; }
    return dispatch_line(line, (uint16_t)n);
}

x72_status_t x72_feed(uint8_t byte)
{
    /* --- 已经在攒一行 --- */
    if (s_len > 0) {
        if (byte == '\r') return X72_NONE;
        if (s_len >= X72_BUF_SIZE) {
            s_len = 0;
            x72_frames_err++;
            return X72_E_OVERFLOW;
        }
        s_buf[s_len++] = (char)byte;

        if (byte == '\n' || byte == ']' || byte == '}') {
            uint16_t n = s_len;
            x72_status_t st;
            /* 去掉尾部换行 */
            while (n > 0 && (s_buf[n-1] == '\n' || s_buf[n-1] == '\r')) n--;
            s_len = 0;
            if (n == 0) return X72_NONE;
            st = dispatch_line(s_buf, n);
            return st;
        }
        return X72_NONE;
    }

    /* --- 行首：只认起始字符 --- */
    if (byte == '[') {
        s_len = 0;
        s_buf[s_len++] = '[';
        return X72_NONE;
    }
    if (byte == '{') {
        s_len = 0;
        s_buf[s_len++] = '{';
        return X72_NONE;
    }
    return X72_NONE;            /* 行外垃圾字节全部丢弃 */
}

void x72_encode(char *out, uint16_t out_size)
{
    uint8_t  b = (uint8_t)X72_BRIGHT_TO_OUT(x72_state.brightness);
    uint16_t p = x72_state.period_ms;
    if (out_size < 18) { if (out_size) out[0] = '\0'; return; }

    out[0]='['; out[1]='L';
    out[2]=(char)('0' + (b/100)%10);
    out[3]=(char)('0' + (b/10)%10);
    out[4]=(char)('0' + b%10);
    out[5]='0';                                   /* 亮度第 4 位恒为 0 */
    out[6]=(char)('0' + (p/1000)%10);
    out[7]=(char)('0' + (p/100)%10);
    out[8]=(char)('0' + (p/10)%10);
    out[9]=(char)('0' + p%10);
    out[10]='|'; out[11]='A'; out[12]='-'; out[13]='-'; out[14]='-';
    out[15]='|'; out[16]=']'; out[17]='\0';
}

/* ================================================================
 *  呼吸 + 平滑（非阻塞，内部刻度 0..1000）
 * ================================================================
 *  用 millis 推算相位，周期参数 = 真实周期，不随循环速度漂移。
 */
static int16_t tri_wave(uint32_t elapsed_ms, uint16_t period_ms)
{
    uint32_t half, ph;
    int32_t v;

    if (period_ms == 0) return 0;
    half = period_ms / 2u;
    if (half == 0) half = 1;
    ph = elapsed_ms % period_ms;

    if (ph < half) {
        v = (int32_t)((uint32_t)ph * 1000u / half);              /* 0 → 1000 */
    } else {
        v = (int32_t)((uint32_t)(period_ms - ph) * 1000u / half);/* 1000 → 0 */
    }
    if (v > 1000) v = 1000;
    return (int16_t)v;
}

void x72_effect_tick(uint32_t now_ms)
{
    static uint32_t s_last_ms = 0;
    uint16_t want;
    int16_t diff;

    if (!x72_state.valid) return;

    /* ------------------------------------------------------------
     * 时间保护（v0.2 新增）
     * ------------------------------------------------------------
     * 主循环是全速空转的，同一毫秒内会调用本函数几百上千次。
     * 如果不挡住，平滑逻辑会按"调用次数"推进而不是"按时间"推进，
     * 表现就是亮度瞬间跳变、平滑完全失效。
     * ------------------------------------------------------------ */
    if (now_ms == s_last_ms) return;
    s_last_ms = now_ms;

    /* 参数变化时才重置相位，避免"每帧都重启呼吸"导致抖动 */
    if (x72_state.dirty) {
        x72_state.dirty = 0;
        if (x72_state.period_ms != s_breath_period) {
            s_breath_period = x72_state.period_ms;
            s_breath_t0 = now_ms;
        }
        if (x72_state.brightness != s_bright_target) {
            s_bright_target = x72_state.brightness;
            if (s_breath_period != 0) s_breath_t0 = now_ms;
        }
    }

    /* 目标亮度（内部刻度 0..1000） */
    if (s_breath_period == 0) {
        want = s_bright_target;
    } else {
        int16_t w = tri_wave(now_ms - s_breath_t0, s_breath_period);
        want = (uint16_t)(((int32_t)w * (int32_t)s_bright_target) / 1000);
    }

    /* 平滑跟随（v0.2）：固定 1 级/毫秒（内部刻度）。
     * 0→1000 用时 1 秒；呼吸 2 秒周期时每半周才差 1000，
     * 平滑不会拖慢呼吸，只在"切换亮度"时起到缓冲作用。
     */
    diff = (int16_t)want - (int16_t)s_bright_now;
    if (diff > 0) {
        s_bright_now++;
    } else if (diff < 0) {
        s_bright_now--;
    }

    if (s_bright_now != s_last_pwm) {
        s_last_pwm = s_bright_now;
        x72_led_write(s_bright_now);
    }
}

uint16_t x72_effect_brightness(void)
{
    return s_bright_now;
}
