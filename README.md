# gpt-register-bot

企业级分层结构的 FastAPI Web 控制台，用于管理 OpenAI 账号注册任务。

## 目录结构（分层架构）

```text
gpt-register-bot/
├─ src/gpt_register_bot/
│  ├─ config/                      # 全局配置（pydantic-settings）
│  │  └─ settings.py
│  ├─ domain/                      # 领域层：纯模型 + 端口（无 I/O / 框架依赖）
│  │  ├─ models.py                 # TempMailbox / OAuthStart / RegistrationResult
│  │  └─ ports.py                  # HttpClient / MailProvider / TokenRepository 协议
│  ├─ application/                 # 应用层：用例编排（只依赖 domain 端口）
│  │  ├─ registration_service.py   # 注册主流程（拆分后的用例）
│  │  ├─ run_executor.py           # 并发执行器
│  │  ├─ job_manager.py            # 任务生命周期
│  │  ├─ logging_buffer.py         # LogBuffer + LogBufferHandler
│  │  └─ dto.py                    # 任务请求/状态 DTO
│  ├─ infrastructure/              # 基础设施层：端口的具体适配器
│  │  ├─ http_client.py            # CurlHttpClient（curl_cffi 指纹模拟）
│  │  ├─ mail.py                   # MailTmProvider + Strategy 注册表
│  │  ├─ oauth.py                  # OAuthClient（PKCE）
│  │  ├─ cpa.py                    # CpaUploader
│  │  └─ persistence.py            # FileTokenRepository
│  ├─ interfaces/                  # 接口层：交付方式
│  │  ├─ web/                      # FastAPI 控制台（api/main/schemas/dependencies/ui）
│  │  └─ cli.py                    # CLI 入口
│  └─ container.py                 # 组合根（依赖注入装配）
├─ tests/                          # 单元 / mock 集成测试
├─ web_app.py                      # Web 入口（Docker / uvicorn）
└─ pyproject.toml
```

## 分层职责

| 层 | 职责 | 依赖方向 |
|---|---|---|
| `domain/` | 纯模型与端口（接口），无任何 I/O | 不依赖任何层 |
| `application/` | 用例编排、并发控制、任务生命周期 | 仅依赖 `domain` |
| `infrastructure/` | 端口的具体实现（HTTP、邮箱、OAuth、持久化、日志） | 依赖 `domain` |
| `interfaces/` | Web / CLI 交付适配 | 依赖 `application` |
| `container.py` | 组合根：将适配器装配进应用服务 | 连接各层 |
| `config/` | 环境变量与默认值集中管理 | 被各层引用 |

> 采用的设计模式：**依赖倒置/端口适配器**（domain 定义协议，infrastructure 实现）、
> **Strategy + Registry**（`infrastructure/mail.py` 可插拔邮箱提供商）、
> **依赖注入**（`container.py` 组合根，无全局单例耦合）、
> **Repository**（`TokenRepository` 抽象输出落盘）。

## 安装

```bash
uv sync
uv sync --extra dev   # 含测试依赖
```

## 启动

```bash
# Web 控制台
uv run uvicorn web_app:app --host 0.0.0.0 --port 8000

# 或使用项目脚本
uv run gpt-register-web

# CLI 模式（三线程循环注册）
uv run gpt-register-cli --proxy http://127.0.0.1:7890
```

浏览器访问 [http://127.0.0.1:8000](http://127.0.0.1:8000)

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `GPT_REGISTER_HOST` | `0.0.0.0` | Web 绑定地址 |
| `GPT_REGISTER_PORT` | `8000` | Web 端口 |
| `GPT_REGISTER_OUTPUT_DIR` | `./output` | 输出目录 |
| `GPT_REGISTER_DEFAULT_CONCURRENCY` | `3` | 默认并发数 |

## Docker

```bash
docker compose up -d --build
```

## 测试

```bash
uv run pytest
```

## API 参数

- `total_runs`：总执行次数
- `concurrency`：并发线程数（默认 3）
- `proxy`：HTTP 代理（可选）
- `cpa_url` + `cpa_token`：CPA 上传（需同时提供）

输出文件写入 `output/token_*.json` 与 `output/accounts.txt`。
