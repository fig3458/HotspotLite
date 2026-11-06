# HotspotLite

轻量 **Windows 10 / 11 移动热点**助手：开/关热点、改 SSID 与密码、查看已连接客户端，支持登录后自动开热点。无托盘常驻依赖。

通过系统 WinRT `NetworkOperatorTetheringManager` 控制移动热点。

## 功能

| 能力 | 说明 |
|------|------|
| 状态查看 | 当前开/关状态、SSID、密码、客户端数 |
| 一键开关 | 开启 / 关闭移动热点 |
| 改配置 | 修改 SSID、密码并保存 |
| 开机自启 | 可选注册计划任务，登录后自动开热点 |

## 环境要求

- Windows 10 / 11（需系统自带「移动热点」能力）
- 本机先有可用的有线或 Wi‑Fi 出网连接
- 部分操作可能需要管理员权限

## 下载与使用

1. 到 [Releases](https://github.com/fig3458/HotspotLite/releases) 下载 `HotspotLite.exe`
2. 双击运行，按界面开/关或改 SSID/密码
3. 需要自启时，在界面勾选并允许创建计划任务

源码运行（Python 3.10+，标准库 + tkinter）：

```bat
python hotspot_lite.py
```

## 自行打包

```powershell
.\build.ps1
```

产物：`dist\HotspotLite.exe`

## 配置文件

`%APPDATA%\HotspotLite\config.json`

## 许可证

[MIT](LICENSE)
