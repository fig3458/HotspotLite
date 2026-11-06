# HotspotLite

轻量 Windows 10/11 **移动热点**助手：开/关热点、改 SSID/密码、查看连接客户端，支持计划任务开机自启。无托盘常驻依赖。

通过 WinRT `NetworkOperatorTetheringManager` 控制系统移动热点。

## 功能

- 查看当前热点状态、SSID、密码、已连接客户端数
- 一键开启 / 关闭热点
- 修改 SSID 与密码并保存到本地配置
- 可选注册计划任务：登录后自动开热点

## 下载与使用

1. 到 [Releases](../../releases) 下载 `HotspotLite.exe`（推荐），或源码运行
2. 本机需先有可用的有线 / Wi‑Fi 出网连接
3. 部分环境修改热点配置需要管理员权限

源码运行（Python 3.10+，标准库 + tkinter）：

```bat
python hotspot_lite.py
```

## 自行打包

```powershell
.\build.ps1
```

产物：`dist\HotspotLite.exe`

## 配置

配置文件：`%APPDATA%\HotspotLite\config.json`
