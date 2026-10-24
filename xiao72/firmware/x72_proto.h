/**
 * x72_proto.h — 小72 灯控协议（MCU 侧，不依赖任何平台）
 * ========================================================
 * 两种输入格式都支持，按首字符自动分派：
 *
 *   A) 紧凑帧（PC 自动发送用，17 字节）
 *        [ L bbbb pppp | A --- | ]
 *        bbbb = 亮度 0..100（4 位左补零）
 *        pppp = 呼吸周期 ms（4 位左补零，0000 = 常亮）
 *
 *   B) JSON（手敲调试用，好读）
 *        {"led":50,"period":2000}
 *        字段顺序任意，缺字段 = 保持不变；只有 {"led":50} 就只改亮度。
 *
 * ★ 亮度有两套刻度，改代码时别搞混：
 *      对外（协议/显示）  0..100
 *      内部（计算/PWM）   0..1000   = 对外 × 10
 *   写协议解析时用 100 刻度，写呼吸/平滑时用 1000 刻度。
 *
 * 设计约束（F103C8T6：64KB Flash / 20KB RAM）：
 *   零动态内存；零 printf/sscanf；解析器约 2KB。
 */
#ifndef X72_PROTO_H
#define X72_PROTO_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ---------------- 亮度刻度 ---------------- */
#define X72_BRIGHT_OUT_MAX   100    /* 协议/显示刻度 */
#define X72_BRIGHT_IN_MAX    1000   /* 内部计算/PWM 刻度 */

/* ---------------- 状态：MCU 侧唯一的"真相" ---------------- */
typedef struct {
    uint16_t brightness;    /* ★ 内部刻度 0..1000（对外 0..100 的是它的 1/10） */
    uint16_t period_ms;     /* 0 = 常亮；>0 = 呼吸周期 */
    uint8_t  valid;         /* 是否收到过至少一帧合法帧 */
    uint8_t  dirty;         /* 刚被更新，需要重设效果   */
} x72_state_t;

typedef enum {
    X72_OK        = 0,   /* 收到并应用了一帧             */
    X72_NONE      = 1,   /* 还没攒够一帧，继续喂字节      */
    X72_E_FRAME   = 2,   /* 格式错误，状态未变           */
    X72_E_OVERFLOW= 3,   /* 超长，缓冲已清空             */
} x72_status_t;

extern volatile x72_state_t x72_state;

/* 调试计数（OLED / 串口回显用） */
extern volatile uint16_t x72_frames_ok;
extern volatile uint16_t x72_frames_err;

/* ---------------- 解析 ---------------- */

void x72_reset(void);

/**
 * 喂一个字节（可在 USART 中断或主循环里调用，不阻塞）。
 */
x72_status_t x72_feed(uint8_t byte);

/** 直接解析一行字符串（测试/调试用，绕过串口） */
x72_status_t x72_parse_line(const char *line);

/** 把当前状态编码回紧凑帧（应答/回显用） */
void x72_encode(char *out, uint16_t out_size);

/* ---------------- 效果 ---------------- */

/** 每 1ms 调用一次。内部会挡住同毫秒的重复调用。 */
void x72_effect_tick(uint32_t now_ms);

/** 当前实际输出亮度，**内部刻度 0..1000**（显示时自己去 /10） */
uint16_t x72_effect_brightness(void);

/* ---------------- 平台钩子（由 x72_port.c 实现） ---------------- */
uint32_t x72_tick_ms(void);              /* 毫秒计时                     */
void     x72_led_write(uint16_t level);  /* 内部刻度 0..1000 → PWM       */
void     x72_on_error(x72_status_t err); /* 错误上报（可空）             */

/* ---------------- 身份握手（v0.4） ----------------
 * PC 发 "[I?"，设备回 "[I <id>|<model>|<版本>|<能力清单>]"
 * 目的：CH340 这类芯片没有 USB 序列号，靠设备自报身份来区分多台设备。
 * 身份可在编译选项里覆盖，不用改源码。
 */
#define X72_PROTO_VER    "1.0"

#ifndef X72_DEVICE_ID
#define X72_DEVICE_ID    "x72-led"
#endif
#ifndef X72_DEVICE_MODEL
#define X72_DEVICE_MODEL "X72-LED"
#endif
#ifndef X72_DEVICE_CAPS
#define X72_DEVICE_CAPS  "led,brightness,period"
#endif

/** 平台钩子：阻塞发送一行（不含换行符）。由 USART1.c 实现。 */
void x72_send_line(const char *line);

/* 仅 PC 模拟器使用：见 x72_proto.c 的 X72_NO_PORT 分支 */
void x72_sim_set_tick(uint32_t t);

#ifdef __cplusplus
}
#endif

#endif /* X72_PROTO_H */
