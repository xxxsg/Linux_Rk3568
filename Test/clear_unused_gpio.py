#!/usr/bin/env python3
"""
逐芯片将未被占用且为 output 的 GPIO line 设为 0（逐芯片交互式操作）。
使用前请确认你有 sudo 权限。
用法：
  sudo python3 clear_unused_gpio.py
或先做干跑：
  python3 clear_unused_gpio.py --dry
"""

import subprocess
import re
import sys
from pathlib import Path

def list_chips():
    chips = []
    for path in Path('/dev').glob('gpiochip*'):
        chips.append(path.name)
    return sorted(chips)

def parse_gpioinfo(chip):
    try:
        p = subprocess.run(['gpioinfo', chip], capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"无法运行 gpioinfo {chip}: {e}")
        return []
    lines = []
    for line in p.stdout.splitlines():
        m = re.search(r'line\s+(\d+):\s+.*\bunused\b.*\boutput\b', line)
        if m:
            lines.append(int(m.group(1)))
    return lines

def set_line_zero(chip, line):
    cmd = ['sudo', 'gpioset', chip, f'{line}=0']
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode == 0, p.stdout + p.stderr

def main(dry=False):
    chips = list_chips()
    if not chips:
        print('未找到 /dev/gpiochip*')
        return
    print('发现芯片：', ', '.join(chips))
    for chip in chips:
        print('\n==== 处理芯片:', chip, '====')
        lines = parse_gpioinfo(chip)
        if not lines:
            print('未发现可写的 unused output lines，跳过。')
            continue
        print('以下 unused output lines 将被设为 0:', ','.join(map(str, lines)))
        ans = input('是否对该芯片设置这些线为0？(y/N): ').strip().lower()
        if ans != 'y':
            print('跳过此芯片。')
            continue
        for ln in lines:
            if dry:
                print(f"[DRY] 将执行: gpioset {chip} {ln}=0")
                continue
            ok, out = set_line_zero(chip, ln)
            if ok:
                print(f'已设置 {chip} line {ln} = 0')
            else:
                print(f'设置失败 {chip} line {ln}: {out.strip()}')
        print('该芯片处理完成。按回车继续到下一个芯片。')
        input()

if __name__ == '__main__':
    dry = ('--dry' in sys.argv) or ('-n' in sys.argv)
    try:
        main(dry=dry)
    except KeyboardInterrupt:
        print('\n已取消')
