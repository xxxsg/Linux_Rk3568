# Serial MCP Experiment Config

## 0. 工具选择 (Tool Selection)
> 在其他 PC 上配置时，直接复制本节内容给 AI 即可。

- **MCP Server 名称**: `serial-mcp-server`
- **安装命令**: `pip install serial-mcp-server`
- **OpenCode 配置 Key**: `serial`
- **启动命令**: `python -m serial_mcp_server`

**OpenCode 配置片段 (`opencode.json`)**:
```json
{
  "mcp": {
    "serial": {
      "type": "local",
      "command": ["python", "-m", "serial_mcp_server"],
      "enabled": true
    }
  }
}
```

---

## 1. 实验配置 (Experiment Config)
> 每次实验前更新此部分，AI 将读取此配置并自动执行。

### orange pi4pro

#### 1.1 连接参数
- **Port**: `COM3`
- **Baudrate**: `115200`
- **Data Bits**: `8`
- **Parity**: `None`
- **Stop Bits**: `1`


### rk3568 

#### 1.1 连接参数
- **Port**: `COM10`
- **Baudrate**: `1500000`
- **Data Bits**: `8`
- **Parity**: `None`
- **Stop Bits**: `1`


---

## 2. 常用 Prompt 示例
- **开始实验**: "读取 SERIAL_MCP_SETUP.md 中的配置，连接串口并按表格步骤执行测试。"
- **手动发令**: "发送指令 `START` 并等待 2 秒读取响应。"
- **持续监控**: "连接串口，持续读取并过滤包含 `ERROR` 的日志。"

---

## 3. MCP 支持的工具接口 (Supported Tools)

### 3.1 核心串口操作 (Serial Core)
| 工具名 | 功能描述 | 常用参数示例 |
|---|---|---|
| `serial.list_ports` | 扫描并列出系统可用串口 | 无 |
| `serial.open` | 打开指定串口并建立连接 | `port="COM3"`, `baudrate=115200` |
| `serial.close` | 关闭当前串口连接 | `connection_id="..."` |
| `serial.connection_status` | 检查当前连接是否存活 | `connection_id="..."` |
| `serial.read` | 读取指定字节的原始数据 | `nbytes=1024`, `timeout_ms=1000` |
| `serial.write` | 向串口发送数据 | `data="AT\r\n"`, `as="text"` 或 `as="hex"` |
| `serial.readline` | 读取一行数据 (直到换行符) | `newline="\r\n"` |
| `serial.read_until` | 读取直到遇到特定分隔符 | `delimiter="OK"`, `max_bytes=4096` |
| `serial.flush` | 清空输入/输出缓冲区 | `what="both"` (或 `input`/`output`) |
| `serial.set_dtr` | 设置 DTR 控制线电平 | `value=true` (高) 或 `false` (低) |
| `serial.set_rts` | 设置 RTS 控制线电平 | `value=true` (高) 或 `false` (低) |
| `serial.pulse_dtr` | 脉冲 DTR 线 (常用于硬件复位) | `duration_ms=100` |
| `serial.pulse_rts` | 脉冲 RTS 线 | `duration_ms=100` |

### 3.2 连接管理 (Introspection)
| 工具名 | 功能描述 |
|---|---|
| `serial.connections.list` | 列出所有当前打开的连接及其配置 |

### 3.3 协议规范 (Protocol Specs)
> 用于让 AI 理解特定设备的私有协议，支持创建、注册、加载协议文档。
| 工具名 | 功能描述 |
|---|---|
| `serial.spec.template` | 生成协议规范模板 |
| `serial.spec.register` | 注册一个协议规范文件 |
| `serial.spec.list` | 列出已注册的规范 |
| `serial.spec.attach` | 将规范绑定到当前连接 |
| `serial.spec.get` | 获取当前连接的规范 |
| `serial.spec.read` | 读取规范文件内容 |
| `serial.spec.search` | 在规范中搜索关键词 |

### 3.4 调试与追踪 (Tracing)
| 工具名 | 功能描述 |
|---|---|
| `serial.trace.status` | 查看追踪日志状态和事件数 |
| `serial.trace.tail` | 查看最近的工具调用事件记录 |

### 3.5 插件管理 (Plugins)
| 工具名 | 功能描述 |
|---|---|
| `serial.plugin.template` | 生成 Python 插件模板 |
| `serial.plugin.list` | 列出已加载的插件 |
| `serial.plugin.reload` | 热重载指定插件 |
| `serial.plugin.load` | 从路径加载新插件 |
