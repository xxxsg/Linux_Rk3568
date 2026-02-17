# ============================================================================
# Makefile - I2C 设备动态注册驱动编译文件
# ============================================================================

# 模块名称
obj-m += i2c_devices_register.o

# 内核目录（根据实际内核版本调整）
KERNEL_DIR := /lib/modules/$(shell uname -r)/build

# 当前目录
PWD := $(shell pwd)

# 编译器
CC := $(CROSS_COMPILE)gcc

# 默认目标：编译内核模块
all:
	@echo "========== 开始编译 I2C 驱动模块 =========="
	make -C $(KERNEL_DIR) M=$(PWD) modules
	@echo "========== 编译完成 =========="

# 清理目标：删除编译生成的文件
clean:
	@echo "========== 清理编译文件 =========="
	make -C $(KERNEL_DIR) M=$(PWD) clean
	rm -f *.o *.ko *.mod.c *.mod *.order *.symvers
	@echo "========== 清理完成 =========="

# 安装目标：将模块复制到系统模块目录
install:
	@echo "========== 安装模块 =========="
	cp i2c_devices_register.ko /lib/modules/$(shell uname -r)/kernel/drivers/i2c/
	depmod -a
	@echo "========== 安装完成 =========="

# 加载目标：加载内核模块
load:
	@echo "========== 加载模块 =========="
	insmod i2c_devices_register.ko
	dmesg | tail -20
	@echo "========== 加载完成 =========="

# 卸载目标：卸载内核模块
unload:
	@echo "========== 卸载模块 =========="
	rmmod i2c_devices_register
	dmesg | tail -10
	@echo "========== 卸载完成 =========="

# 帮助信息
help:
	@echo "可用目标:"
	@echo "  make all      - 编译模块"
	@echo "  make clean    - 清理文件"
	@echo "  make install  - 安装模块"
	@echo "  make load     - 加载模块"
	@echo "  make unload   - 卸载模块"