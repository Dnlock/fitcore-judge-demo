# Fitcore 健身豆 | ANKER 黑客松评委演示源码

> 参赛团队：练的对练的好队 · 赛道：智能录音  
> 核心目标：让每一次训练都被记录、理解和复盘。

**重要：本仓库的在线评委 Demo 使用 FAKE_TEST 确定性测试 ASR + fake 语义 Provider，不调用真实 ASR/大模型，不连接实体 Soundcore D3200。** 它用于验证完整的音频上传、异步作业、训练事实与复盘业务流程，不能当作真实设备端到端识别效果的证明。

## 项目解决什么问题

力量训练时频繁操作手机记录动作、重量和次数，会打断训练；组间的主观感受也难以沉淀。Fitcore 采用智能录音作为潜在采集入口，将语音转换为结构化训练事实，通过待确认机制避免把计划、模糊表达或未完成动作误写成已完成训练，并在训练结束后提供数据复盘。

## 在线体验

- [Fitcore 评委在线 Demo（Launch SIT）](https://sit-p-18126161195-fitcore-judge-demo-hackathon.anker-launch.com)
- 浏览器打开后：开始训练 → 选择预置测试 WAV 并提交 → 等待 Audio Job 完成 → 查看 Facts / Pending → Finish → Review。
- 如果链接不可访问，请使用下方 Docker 本地启动。公开网址是部署交接记录中的地址，**本 README 不声称当前时刻已重新验证可用性**。

### 哪些是实测，哪些是演示

| 能力 | 交付状态 |
| --- | --- |
| HTTP 创建训练 Session、完整 WAV 上传、查询 Audio Job | 在评委隔离栈已有自动化验证记录 |
| 训练 Facts / Pending / Events / Finish / Review | 在评委隔离栈已有自动化验证记录 |
| 固定测试音频到固定转录文本 | **FAKE_TEST**，不是实时 AI 识别 |
| D3200 → iPhone 音频 → 真实云端 ASR → 训练记录 | 不属于本仓库已验证链路，待真机端到端验收 |
| 长期训练记忆、下一组个性化建议 | 产品演进方向，不等同于本 Demo 已交付功能 |
| 用户级生产认证、完整隐私/保留策略 | 本 Demo 不代表生产环境已经实现 |

具体说明见 [音频技术架构与证据边界](docs/AUDIO_ARCHITECTURE.md)。

## 本仓库技术架构

```text
评委 Web 浏览器（同源页面，无法读取后端 Bearer Token）
        │
        ▼
Web /realproxy（受控路由与方法白名单、限流）
        │ 服务端持有唯一测试 Token
        ▼
隔离 FastAPI Core（127.0.0.1:8001，仅容器内部可达）
        │
        ├── Session + Audio Job → SQLite 持久化队列
        ├── FAKE_TEST 确定性测试 ASR
        ├── fake 语义解析 / Training Context / Fact Engine
        └── Events / Facts / Pending / Finish / Review
        │
        ▼
浏览器交互显示记录和复盘
```

主业务代码由 `fitcore-core-real/app/` 的固定版本快照提供；公开 Demo 不连接生产业务数据库，也不共享生产模型凭据。

## 本地安装与运行

要求：安装 Docker，使用 Bash / macOS / Linux shell。以下只是隔离测试环境，不应在公网暴露。

```bash
git clone https://github.com/Dnlock/fitcore-judge-demo.git
cd fitcore-judge-demo
docker build -t fitcore-judge-demo:local .
# 临时本机测试凭据；不要提交到仓库，也不要写进网页代码
TEST_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
docker run --rm -p 127.0.0.1:8080:80 \
  -e REAL_API_TOKEN="$TEST_TOKEN" \
  -e FITCORE_HTTP_API_TOKEN="$TEST_TOKEN" \
  --tmpfs /data:rw,size=64m \
  fitcore-judge-demo:local
```

在浏览器打开 <http://127.0.0.1:8080/>，按页面引导操作；另外打开 <http://127.0.0.1:8080/health> 检查服务健康。本地 Docker 过程依赖镜像构建和环境配置，本文命令不代表已在每个用户平台重新运行验证。真实正式部署请使用服务端密钥管理，不能直接照搬测试开关。

## 代码目录说明

| 目录/文件 | 用途 |
| --- | --- |
| `web/` | 评委 UI：HTML、CSS、JS |
| `proxy/` | 同源代理、安全白名单、服务端凭据注入 |
| `core/` | 隔离 Core 启动器与 FAKE_TEST 测试 ASR |
| `fitcore-core-real/app/` | 固定版训练业务 Core 代码快照 |
| `fixtures/wav/` | 映射测试用的演示 WAV；不代表真人实时录音 |
| `e2e/` | 完整链路、安全与隔离回归脚本 |
| `evidence/` | 历史本地测试证据；不是在线服务实时监控 |
| `Dockerfile`, `entrypoint.sh` | 单容器启动、内部 Core 与对外代理 |
| `env.example` | 配置字段示例；真实密钥禁止提交 |
| `JUDGE_CORE_CONFIG.md` | Demo 安全边界、配置说明与测试门禁 |
| `docs/AUDIO_ARCHITECTURE.md` | D3200 / iOS / ASR / Core 架构与当前实现差异 |
| `docs/REPOSITORY_STATUS.md` | 相关仓库、重要分支与验收声明 |

## 验证与限制

交接记录报告：公网隔离 Demo 的安全门禁 **12/12**、E2E **21/21**；仓库的本地 `e2e/smoke_e2e.py` 另有 28 步脚本说明。上述为**已有交接/测试报告**，本次整理文档未重跑这些测试。对于本仓库未提交的 Xcode 真机录音、实际用户语音识别准确率及跨设备同步情况，不作成功声明。

**当前不包含**：Soundcore SDK 私有二进制与协议资料、真人录音、私有服务器密钥。源码公开前仍需复核历史提交、测试音频来源与敏感信息；不要仅凭本 README 断言整个仓库已完成安全审计。

## 代码合规与隐私

- 不在前端、Git 历史或诊断日志中写入 API Key、Bearer Token、SDK License、真实音频或可识别个人信息。
- 测试演示采用独立 SQLite；原始完整 WAV 在音频 Job 流程中可能持久化，本版本尚不能声明自动删除周期，禁止用于未经授权的私人录音。
- `AUDIO_TEST_SOURCE_TRUSTED=true` 仅限受控测试，它不构成声纹认证或真实用户身份验证。
- Soundcore SDK 及设备通信细节属于受限第三方依赖，**不在公开仓库分发**。

## 相关工程（部分为非公开分支）

- iOS App：`Dnlock/fitcore-ios`（实际集成代码在 `lhy/*`、`handoff/*` 等分支；`main` 仍是精简基线）
- 后端研发：`Dnlock/fitcore-core`（完整 WAV HTTP 在 `feature/wav-http` 及后续集成分支，不等于 `main` 已合并）
- UI 预览：`Dnlock/fitcore-judge-demo-ui-preview`（独立 UI 改版预览，不等于当前正式演示已替换）
