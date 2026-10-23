/**
 * sim_main.c — PC 模拟器：在电脑上验证 C 解析器（不需要单片机）
 * ==============================================================
 * 编译（任选其一）：
 *   MSVC : cl /nologo /wd4819 /DX72_NO_PORT /Fe:sim.exe sim_main.c x72_proto.c
 *   MinGW: gcc -DX72_NO_PORT -I. sim_main.c x72_proto.c -o sim.exe
 *
 * 用法：
 *   sim.exe --selftest          跑内置测试向量（帧 + JSON + 脏输入）
 *   sim.exe --demo-breath 2000  打印一个呼吸周期的亮度曲线
 *   echo [L00502000|A---|] | sim.exe
 *   echo {"led":50,"period":2000} | sim.exe
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "x72_proto.h"

static uint16_t g_last_pwm = 0;

/* ---- 平台钩子（模拟器实现） ---- */
void x72_led_write(uint16_t level) { g_last_pwm = level; }
void x72_on_error(x72_status_t err) { (void)err; }

static void print_state(void)
{
    printf("STATE brightness=%u period_ms=%u valid=%u\n",
           (unsigned)(x72_state.brightness / 10u),
           (unsigned)x72_state.period_ms,
           (unsigned)x72_state.valid);
}

/* ---------------- 自检 ---------------- */
static int run_vectors(void)
{
    struct {
        const char *input;
        int expect_ok;
        int expect_b;
        int expect_p;
    } t[] = {
        /* ---- 紧凑帧（expect_b 是内部刻度 = 协议值 x10） ---- */
        { "[L00502000|A---|]",           1,  500, 2000 },
        { "[L01000000|A---|]",           1, 1000,    0 },
        { "[L01500000|A---|]",           1, 1000,    0 },   /* 限幅到 100 */
        { "[L-1x2000|A---|]",            0,   -1,   -1 },
        { "junk junk[L00300500|A---|]",  1,  300,  500 },
        { "[L00300500|A---",             1,  300,  500 },   /* 无帧尾宽容 */
        { "[L00300500]",                 0,   -1,   -1 },   /* 段数不足 */
        { "[L00000000|A---|]",           1,    0,    0 },
        { "[L10099990|A---|]",           1, 1000, 9990 },
        { "[L00991230|A---|]",           1,  990, 1230 },

        /* ---- JSON ---- */
        { "{\"led\":50,\"period\":2000}",  1,  500, 2000 },
        { "{\"period\":1000,\"led\":80}",  1,  800, 1000 },
        { "{ \"led\" : 20 , \"period\" : 500 }", 1, 200, 500 },
        { "{\"led\":150}",              1, 1000,    0 },   /* 限幅 */
        { "{\"led\":0}",                1,    0,    0 },
        { "{\"period\":0}",             1,    0,    0 },
        { "{\"foo\":1}",                0,   -1,   -1 },
        { "{\"led\":}",                 0,   -1,   -1 },
        { "{bad json}",                  0,   -1,   -1 },

        /* ---- 完全不像的输入 ---- */
        { "hello world",                 0,   -1,   -1 },
        { "",                            0,   -1,   -1 },
    };
    int pass = 0, fail = 0;
    unsigned i;

    for (i = 0; i < sizeof(t)/sizeof(t[0]); i++) {
        x72_status_t st;
        int ok, good;

        x72_state.valid = 0;
        x72_state.brightness = 0;
        x72_state.period_ms = 0;

        st = x72_parse_line(t[i].input);
        ok = (st == X72_OK);
        good = (ok == t[i].expect_ok);
        if (good && ok) {
            good = (x72_state.brightness == (uint16_t)t[i].expect_b)
                && (x72_state.period_ms == (uint16_t)t[i].expect_p);
        }
        printf("[%s] %-32s st=%d b=%u p=%u\n", good ? "PASS" : "FAIL",
               t[i].input, (int)st,
               (unsigned)(x72_state.brightness / 10u), (unsigned)x72_state.period_ms);
        if (good) pass++; else fail++;
    }

    printf("\nselftest: %d passed, %d failed\n", pass, fail);
    return fail == 0 ? 0 : 1;
}

/* ---------------- 呼吸演示 ---------------- */
static void demo_breath(int period_ms)
{
    uint32_t t, next = 0;
    printf("\n-- breath demo period=%dms --\n", period_ms);

    x72_state.valid = 1;
    x72_state.brightness = 1000;
    x72_state.period_ms = (uint16_t)period_ms;
    x72_state.dirty = 1;
    x72_sim_set_tick(0);

    for (t = 0; t <= (uint32_t)period_ms * 2u; t++) {
        int n, k;
        x72_sim_set_tick(t);
        x72_effect_tick(t);
        if (t >= next) {
            uint16_t v = (uint16_t)(x72_effect_brightness() / 10u);
            printf("%5ums ", (unsigned)t);
            n = v / 2;
            for (k = 0; k < n; k++) putchar('#');
            printf(" %u%%\n", (unsigned)v);
            next += 100;
        }
    }
}

int main(int argc, char **argv)
{
    if (argc > 1 && strcmp(argv[1], "--selftest") == 0) {
        return run_vectors();
    }
    if (argc > 1 && strcmp(argv[1], "--demo-breath") == 0) {
        int p = (argc > 2) ? atoi(argv[2]) : 2000;
        demo_breath(p > 0 ? p : 2000);
        return 0;
    }

    {
        char line[160];
        int any = 0;
        while (fgets(line, sizeof(line), stdin)) {
            size_t n = strlen(line);
            size_t k;
            x72_status_t st = X72_NONE;

            while (n > 0 && (line[n-1] == '\n' || line[n-1] == '\r')) line[--n] = '\0';
            if (n == 0) continue;
            any = 1;

            /* 走真实路径：逐字节 feed，和 USART 中断完全一致 */
            x72_reset();
            for (k = 0; k < n; k++) {
                x72_status_t r = x72_feed((uint8_t)line[k]);
                if (r != X72_NONE) st = r;
            }
            if (st == X72_NONE) st = X72_E_FRAME;
            printf("FRAME %d | ", (int)st);
            print_state();
        }
        if (!any) {
            printf("usage: sim.exe --selftest | --demo-breath [ms] | echo \"[L00502000|A---|]\" | sim.exe\n");
        }
    }
    return 0;
}
