# gpt-register-bot

一个只保留 **Web 页面逻辑** 的 FastAPI 项目，采用 `src` 标准布局与分层设计。

## 目录结构

```text
gpt-register-bot/
├─ src/
│  └─ gpt_register_bot/
│     └─ web/
│        ├─ api.py                  # API 路由层
│        ├─ config.py               # 配置层
│        ├─ schemas.py              # 数据模型层
│        ├─ main.py                 # 应用装配层
│        ├─ services/
│        │  ├─ log_buffer.py        # 日志缓存服务
│        │  └─ process_manager.py   # 运行状态服务
│        └─ ui/
│           ├─ templates/index.html # 页面模板
│           └─ static/
│              ├─ style.css         # 样式
│              └─ app.js            # 前端交互
├─ web_app.py                       # Web 入口兼容文件
├─ pyproject.toml
└─ README.md
```

## 分层说明（SRP）

- `api.py`：只处理 HTTP 请求和状态码映射。
- `schemas.py`：只定义请求/响应模型。
- `process_manager.py`：只管理运行状态与任务生命周期。
- `log_buffer.py`：只负责线程安全日志存储。
- `main.py`：只负责组装 FastAPI app（路由 + 静态资源）。
- `ui/*`：只负责页面展示与前端交互。

## 安装依赖

```bash
uv sync
```

## 启动项目

```bash
uv run uvicorn web_app:app --host 0.0.0.0 --port 8000
```

浏览器访问：

```text
http://127.0.0.1:8000
```

## 项目脚本

```bash
uv run gpt-register-web
```

## 当前行为说明

当前 Web 后端会在服务层内直接调用 `source.py` 的核心逻辑（不再通过子进程），并通过 FastAPI 控制任务生命周期：

- `total_runs`：本次总生成次数
- `concurrency`：并发线程数（默认 `3`，前端不传时使用默认值）
- `cpa_url` + `cpa_token`：可选 CPA 上传配置（需同时提供）

日志会被统一写入内存日志缓冲，接口实时返回，中文日志在 Web 端按 UTF-8 显示，避免乱码。
