# Stock Monitor A (A股实时行情监测与提醒工具)

这是一个基于 PyQt5 的 A 股实时行情监测与提醒工具。支持自选股的实时价格获取、涨跌幅显示，并可针对特定股票设置价格和涨跌幅的提醒阈值。

## 功能特点

- **实时行情获取**：基于腾讯/新浪等公开 API 接口，低延迟获取 A 股（沪市、深市、京市）的最新价格与涨跌幅。
- **自选股管理**：支持模糊搜索添加股票、双击修改提醒条件、一键删除等功能。
- **自定义刷新率**：可在界面直接设置刷新频率（最低 3 秒），满足不同交易频度的监控需求。
- **智能预警提醒**：
  - 价格上涨至设定值 (¥)
  - 价格下跌至设定值 (¥)
  - 涨幅超过设定百分比 (%)
  - 跌幅超过设定百分比 (%)
- **多条提醒**：每只股票可以维护多条提醒，每条提醒可单独选择是否发送邮件。
- **窗口强提醒**：当触发预警时，会自动弹出置顶提示框并播放提示（窗口闪烁），同时自动重置该股票的提醒设置，防止重复弹窗打扰。
- **邮件通知**：可在界面中配置 SMTP 发件邮箱，触发预警时后台发送邮件，不阻塞行情刷新和弹窗提醒。
- **休市暂停刷新**：非 A 股连续竞价时段会显示休市/停盘状态，暂停行情请求，待下一个开盘时间自动恢复刷新。
- **本地持久化**：自选股列表及配置自动保存到本地 `stocks_config.json` 文件中，下次启动自动加载。
- **精致现代 UI**：采用深色主题（Catppuccin Mocha 色调风格）设计，红涨绿跌，数据加粗高亮，清晰美观。

## 运行环境

- Windows (已配置快速启动脚本 `start_monitor.bat`)
- Python 3.x
- 依赖库：`PyQt5`, `requests`
- 推荐使用项目专属 conda 环境：`.conda_env`

## 安装与启动

1. 安装依赖包：
   ```bash
   pip install PyQt5 requests
   ```

2. 启动应用：
   - 双击运行 `start_monitor.bat`
   - 或者在命令行执行：
     ```bash
     python stock_monitor.py
     ```

当前项目已配置本地 conda 环境，双击 `start_monitor.bat` 会优先使用 `.conda_env\pythonw.exe` 启动。手动启动可执行：

```powershell
D:\zhugq\1_project\10_tools\01_Stock-Monitor-A\.conda_env\python.exe stock_monitor.py
```

如果需要在另一台电脑重建环境，可以在项目目录运行：

```powershell
conda env create -p .\.conda_env -f environment.yml
```

## 邮件通知配置

在主界面点击“邮件设置”，填写并启用邮件通知。一般需要准备：

- 发件邮箱地址
- SMTP 服务器和端口，例如 QQ 邮箱常用 `smtp.qq.com:465`，163 邮箱常用 `smtp.163.com:465`
- 邮箱 SMTP 授权码或专用应用密码，不建议使用网页登录密码
- 收件人邮箱，多个收件人用逗号分隔

邮箱相关信息会保存到本地 `email_config.json`，不会写入 `stocks_config.json`。`email_config.json` 已加入 `.gitignore`，上传 GitHub 时不会包含邮箱和授权码。仓库中只保留 `email_config.example.json` 作为示例。

授权码可以直接保存在本地 `email_config.json`，也可以设置“授权码环境变量”，让程序从系统环境变量读取，进一步避免把授权码写入文件。

## 刷新时段

程序只在工作日 A 股连续竞价时段请求行情数据：

- 上午：09:30-11:30
- 下午：13:00-15:00

午间休市、盘后、周末会在状态栏和股票状态列显示休市/停盘，并暂停行情请求。当前未接入法定节假日交易日历，如遇调休或交易所临时休市，需要以后再接入交易日历文件或接口。

## 项目结构

```text
├── stock_monitor.py      # 主程序代码 (PyQt5 界面及业务逻辑)
├── environment.yml       # conda 环境依赖说明
├── email_config.example.json # 邮箱配置示例，不含授权码
├── stocks_config.json    # 本地自选股及刷新率配置文件 (自动生成)
├── start_monitor.bat     # Windows 快捷启动脚本
├── test_sina.py          # 新浪接口测试脚本
├── test_eastmoney.py     # 东方财富接口测试脚本
└── .gitignore            # Git 忽略文件配置
```
