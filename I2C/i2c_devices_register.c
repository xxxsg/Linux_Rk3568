/*
 * ============================================================================
 * 文件名：i2c_devices_register.c
 * 功能：RK3568 平台 I2C 设备动态注册驱动
 * 支持设备：TCA9555(0x20)、PCF8574(0x21)、ADS1115(0x48)
 * 平台：RK3568 ARM64 Ubuntu 20
 * ============================================================================
 */

#include <linux/module.h>       /* 模块支持 */
#include <linux/kernel.h>       /* 内核支持 */
#include <linux/init.h>         /* 初始化支持 */
#include <linux/i2c.h>          /* I2C 核心支持 */
#include <linux/slab.h>         /* 内存分配 */
#include <linux/of.h>           /* 设备树支持 */
#include <linux/gpio.h>         /* GPIO 支持 */
#include <linux/mutex.h>        /* 互斥锁 */

/* 模块信息 */
MODULE_LICENSE("GPL");
MODULE_AUTHOR("KP");
MODULE_DESCRIPTION("RK3568 I2C 设备动态注册驱动");
MODULE_VERSION("1.0");

/* ============================================================================
 * 设备地址定义（7 位 I2C 地址）
 * ============================================================================ */
#define TCA9555_ADDR    0x20    /* TCA9555 GPIO 扩展芯片地址 */
#define PCF8574_ADDR    0x21    /* PCF8574 GPIO 扩展芯片地址 */
#define ADS1115_ADDR    0x48    /* ADS1115 ADC 芯片地址 */

/* ============================================================================
 * I2C 总线配置
 * ============================================================================ */
#define I2C_BUS_NUM     1       /* 使用的 I2C 总线编号（对应/dev/i2c-1） */

/* ============================================================================
 * 全局变量定义
 * ============================================================================ */
static struct i2c_client *g_tca9555_client = NULL;   /* TCA9555 客户端指针 */
static struct i2c_client *g_pcf8574_client = NULL;   /* PCF8574 客户端指针 */
static struct i2c_client *g_ads1115_client = NULL;   /* ADS1115 客户端指针 */

/* ============================================================================
 * TCA9555 设备信息配置
 * ============================================================================ */
static struct i2c_board_info tca9555_info = {
    I2C_BOARD_INFO("tca9555", TCA9555_ADDR),  /* 设备名称和地址 */
};

/* ============================================================================
 * PCF8574 设备信息配置
 * ============================================================================ */
static struct i2c_board_info pcf8574_info = {
    I2C_BOARD_INFO("pcf8574", PCF8574_ADDR),  /* 设备名称和地址 */
};

/* ============================================================================
 * ADS1115 设备信息配置
 * ============================================================================ */
static struct i2c_board_info ads1115_info = {
    I2C_BOARD_INFO("ads1115", ADS1115_ADDR),  /* 设备名称和地址 */
};

/* ============================================================================
 * 函数：i2c_device_read
 * 功能：从 I2C 设备读取数据
 * 参数：client - I2C 客户端指针
 *       reg - 寄存器地址
 *       buf - 数据缓冲区
 *       len - 数据长度
 * 返回：0-成功，负值 - 失败
 * ============================================================================ */
static int i2c_device_read(struct i2c_client *client, u8 reg, u8 *buf, int len)
{
    int ret;
    struct i2c_msg msg[2];

    /* 检查参数有效性 */
    if (!client || !buf || len <= 0) {
        printk(KERN_ERR "[I2C] 参数无效\n");
        return -EINVAL;
    }

    /* 配置写消息（发送寄存器地址） */
    msg[0].addr = client->addr;
    msg[0].flags = 0;                    /* 写操作 */
    msg[0].len = 1;
    msg[0].buf = &reg;

    /* 配置读消息（读取数据） */
    msg[1].addr = client->addr;
    msg[1].flags = I2C_M_RD;             /* 读操作标志 */
    msg[1].len = len;
    msg[1].buf = buf;

    /* 发送 I2C 消息 */
    ret = i2c_transfer(client->adapter, msg, 2);
    if (ret < 0) {
        printk(KERN_ERR "[I2C] 读取失败，地址 0x%02x, 错误码：%d\n", 
               client->addr, ret);
        return ret;
    }

    return 0;
}

/* ============================================================================
 * 函数：i2c_device_write
 * 功能：向 I2C 设备写入数据
 * 参数：client - I2C 客户端指针
 *       reg - 寄存器地址
 *       buf - 数据缓冲区
 *       len - 数据长度
 * 返回：0-成功，负值 - 失败
 * ============================================================================ */
static int i2c_device_write(struct i2c_client *client, u8 reg, u8 *buf, int len)
{
    int ret;
    u8 *tx_buf;
    struct i2c_msg msg;

    /* 检查参数有效性 */
    if (!client || !buf || len <= 0) {
        printk(KERN_ERR "[I2C] 参数无效\n");
        return -EINVAL;
    }

    /* 分配发送缓冲区（寄存器地址 + 数据） */
    tx_buf = kmalloc(len + 1, GFP_KERNEL);
    if (!tx_buf) {
        printk(KERN_ERR "[I2C] 内存分配失败\n");
        return -ENOMEM;
    }

    /* 填充缓冲区 */
    tx_buf[0] = reg;
    memcpy(&tx_buf[1], buf, len);

    /* 配置 I2C 消息 */
    msg.addr = client->addr;
    msg.flags = 0;              /* 写操作 */
    msg.len = len + 1;
    msg.buf = tx_buf;

    /* 发送 I2C 消息 */
    ret = i2c_transfer(client->adapter, &msg, 1);
    if (ret < 0) {
        printk(KERN_ERR "[I2C] 写入失败，地址 0x%02x, 错误码：%d\n", 
               client->addr, ret);
        kfree(tx_buf);
        return ret;
    }

    kfree(tx_buf);
    return 0;
}

/* ============================================================================
 * 函数：tca9555_test
 * 功能：测试 TCA9555 GPIO 扩展芯片
 * 说明：TCA9555 是 16 位 GPIO 扩展器，通过 I2C 控制
 * ============================================================================ */
static int tca9555_test(void)
{
    int ret;
    u8 buf[2];

    if (!g_tca9555_client) {
        printk(KERN_ERR "[TCA9555] 设备未注册\n");
        return -ENODEV;
    }

    /* 读取输入端口 0 的状态 */
    ret = i2c_device_read(g_tca9555_client, 0x00, buf, 1);
    if (ret < 0) {
        printk(KERN_ERR "[TCA9555] 读取输入端口 0 失败\n");
        return ret;
    }
    printk(KERN_INFO "[TCA9555] 输入端口 0 状态：0x%02x\n", buf[0]);

    /* 读取输入端口 1 的状态 */
    ret = i2c_device_read(g_tca9555_client, 0x01, buf + 1, 1);
    if (ret < 0) {
        printk(KERN_ERR "[TCA9555] 读取输入端口 1 失败\n");
        return ret;
    }
    printk(KERN_INFO "[TCA9555] 输入端口 1 状态：0x%02x\n", buf[1]);

    return 0;
}

/* ============================================================================
 * 函数：pcf8574_test
 * 功能：测试 PCF8574 GPIO 扩展芯片
 * 说明：PCF8574 是 8 位 GPIO 扩展器，通过 I2C 控制
 * ============================================================================ */
static int pcf8574_test(void)
{
    int ret;
    u8 buf;

    if (!g_pcf8574_client) {
        printk(KERN_ERR "[PCF8574] 设备未注册\n");
        return -ENODEV;
    }

    /* 读取 GPIO 状态 */
    ret = i2c_device_read(g_pcf8574_client, 0x00, &buf, 1);
    if (ret < 0) {
        printk(KERN_ERR "[PCF8574] 读取 GPIO 状态失败\n");
        return ret;
    }
    printk(KERN_INFO "[PCF8574] GPIO 状态：0x%02x\n", buf);

    /* 写入 GPIO 输出（点亮 LED 示例） */
    buf = 0x01;  /* P0 输出高电平 */
    ret = i2c_device_write(g_pcf8574_client, 0x00, &buf, 1);
    if (ret < 0) {
        printk(KERN_ERR "[PCF8574] 写入 GPIO 失败\n");
        return ret;
    }
    printk(KERN_INFO "[PCF8574] GPIO 输出已设置：0x%02x\n", buf);

    return 0;
}

/* ============================================================================
 * 函数：ads1115_test
 * 功能：测试 ADS1115 ADC 芯片
 * 说明：ADS1115 是 16 位 ADC，通过 I2C 读取模拟量
 * ============================================================================ */
static int ads1115_test(void)
{
    int ret;
    u8 buf[2];

    if (!g_ads1115_client) {
        printk(KERN_ERR "[ADS1115] 设备未注册\n");
        return -ENODEV;
    }

    /* 读取转换寄存器（寄存器地址 0x00） */
    ret = i2c_device_read(g_ads1115_client, 0x00, buf, 2);
    if (ret < 0) {
        printk(KERN_ERR "[ADS1115] 读取转换结果失败\n");
        return ret;
    }

    /* 合并 16 位 ADC 值（高字节在前） */
    printk(KERN_INFO "[ADS1115] ADC 值：0x%02x%02x\n", buf[0], buf[1]);

    return 0;
}

/* ============================================================================
 * 函数：i2c_devices_init
 * 功能：模块初始化函数 - 注册所有 I2C 设备
 * 说明：内核模块加载时自动调用
 * ============================================================================ */
static int __init i2c_devices_init(void)
{
    struct i2c_adapter *adapter;
    int ret;

    printk(KERN_INFO "[I2C] ===== I2C 设备动态注册开始 =====\n");

    /* 步骤 1：获取 I2C 适配器 */
    adapter = i2c_get_adapter(I2C_BUS_NUM);
    if (!adapter) {
        printk(KERN_ERR "[I2C] 获取 I2C-%d 适配器失败\n", I2C_BUS_NUM);
        return -ENODEV;
    }
    printk(KERN_INFO "[I2C] 成功获取 I2C-%d 适配器\n", I2C_BUS_NUM);

    /* ========================================================================
     * 步骤 2：注册 TCA9555 设备
     * ======================================================================== */
    g_tca9555_client = i2c_new_client_device(adapter, &tca9555_info);
    if (IS_ERR(g_tca9555_client)) {
        ret = PTR_ERR(g_tca9555_client);
        printk(KERN_ERR "[I2C] 注册 TCA9555 失败，错误码：%d\n", ret);
        g_tca9555_client = NULL;
    } else {
        printk(KERN_INFO "[I2C] TCA9555 注册成功，地址：0x%02x\n", 
               TCA9555_ADDR);
    }

    /* ========================================================================
     * 步骤 3：注册 PCF8574 设备
     * ======================================================================== */
    g_pcf8574_client = i2c_new_client_device(adapter, &pcf8574_info);
    if (IS_ERR(g_pcf8574_client)) {
        ret = PTR_ERR(g_pcf8574_client);
        printk(KERN_ERR "[I2C] 注册 PCF8574 失败，错误码：%d\n", ret);
        g_pcf8574_client = NULL;
    } else {
        printk(KERN_INFO "[I2C] PCF8574 注册成功，地址：0x%02x\n", 
               PCF8574_ADDR);
    }

    /* ========================================================================
     * 步骤 4：注册 ADS1115 设备
     * ======================================================================== */
    g_ads1115_client = i2c_new_client_device(adapter, &ads1115_info);
    if (IS_ERR(g_ads1115_client)) {
        ret = PTR_ERR(g_ads1115_client);
        printk(KERN_ERR "[I2C] 注册 ADS1115 失败，错误码：%d\n", ret);
        g_ads1115_client = NULL;
    } else {
        printk(KERN_INFO "[I2C] ADS1115 注册成功，地址：0x%02x\n", 
               ADS1115_ADDR);
    }

    /* 释放适配器引用 */
    i2c_put_adapter(adapter);

    /* ========================================================================
     * 步骤 5：测试设备通信（可选）
     * ======================================================================== */
    printk(KERN_INFO "[I2C] 开始设备通信测试...\n");
    
    if (g_tca9555_client)
        tca9555_test();
    
    if (g_pcf8574_client)
        pcf8574_test();
    
    if (g_ads1115_client)
        ads1115_test();

    printk(KERN_INFO "[I2C] ===== I2C 设备动态注册完成 =====\n");

    return 0;
}

/* ============================================================================
 * 函数：i2c_devices_exit
 * 功能：模块退出函数 - 注销所有 I2C 设备
 * 说明：内核模块卸载时自动调用
 * ============================================================================ */
static void __exit i2c_devices_exit(void)
{
    printk(KERN_INFO "[I2C] ===== I2C 设备注销开始 =====\n");

    /* 注销 TCA9555 设备 */
    if (g_tca9555_client) {
        i2c_unregister_device(g_tca9555_client);
        g_tca9555_client = NULL;
        printk(KERN_INFO "[I2C] TCA9555 已注销\n");
    }

    /* 注销 PCF8574 设备 */
    if (g_pcf8574_client) {
        i2c_unregister_device(g_pcf8574_client);
        g_pcf8574_client = NULL;
        printk(KERN_INFO "[I2C] PCF8574 已注销\n");
    }

    /* 注销 ADS1115 设备 */
    if (g_ads1115_client) {
        i2c_unregister_device(g_ads1115_client);
        g_ads1115_client = NULL;
        printk(KERN_INFO "[I2C] ADS1115 已注销\n");
    }

    printk(KERN_INFO "[I2C] ===== I2C 设备注销完成 =====\n");
}

/* 注册模块初始化和退出函数 */
module_init(i2c_devices_init);
module_exit(i2c_devices_exit);