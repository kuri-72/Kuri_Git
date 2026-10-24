/**
 * x72_app.h — 本工程专属的应用层（含 OLED 显示）
 * =================================================
 * 这里放"和这块板子/这个工程强相关"的东西。
 * 通用协议在 x72_proto.c，板级对接在 x72_port.c，两者都不认识 OLED。
 */
#ifndef X72_APP_H
#define X72_APP_H

#include "x72_port.h"

#if X72_USE_OLED
void x72_app_disp_init(void);
void x72_app_disp_tick(uint32_t now_ms);
#endif

#endif /* X72_APP_H */
