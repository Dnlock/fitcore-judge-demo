# Fitcore 音频架构与实际状态（2026-10-17）

## 1. 目标端到端路径

```text
Soundcore D3200 录音豆
  └─ 设备连接 / 采集（Soundcore 官方 SDK + BLE）
       └─ iOS 设备音频回调（部分真机代码仍位于 LHY 本地）
            └─ Opus 数据包 → 解码 PCM16 → 标准化 16kHz / mono / PCM16 WAV
                 └─ HTTPS POST /v1/sessions/{sid}/audio-jobs
                      └─ SQLite 持久化音频 Job + 单实例 Worker
                           └─ 云端真实 ASR → 最终文字
                                └─ 训练语义解析（动作 / 重量 / 次数 / 用户意图）
                                     └─ Guardrail / Training Context / Fact Engine
                                          └─ Facts / Pending / Events / Finish / Review
                                               └─ iPhone 展示训练记录、统计与复盘
```

**这是目标架构，不是已经完成的真实设备端到端验收。** 这里的核心 HTTP 服务接收**完整 WAV 文件**，不是实时流式 ASR 服务。

## 2. 两层互不等同的验证

### A. 真实音频云端业务链（已有本地 HTTP 验收）

后端 `fitcore-core` 分支 `feature/wav-http` 的《稳定基线 WAV HTTP 报告》记录：
- 一条授权真人完整 WAV（5 秒、16kHz、mono、PCM16）上传成功（202）。
- Worker 调用真实 ASR，返回“卧推60公斤做了8个。”；真实 Nova Pro 解析经 Fact Engine 提交 60kg×8。
- Review：1 组、8 次、480kg·次；进程重启后幂等与记录保持。
- 单次验收耗时约 4.37s ASR、6.69s Nova，**不是统计平均延迟或全链路 SLA**。
- 音频来自已准备的 WAV，而非 D3200 真机采集；不证明手机录音豆接入已完成。

上游代码参考：`Dnlock/fitcore-core` 分支 `trae/core-after-r7-20261015` 或后续集成分支。关键文件：
- `app/audio/http.py`：上传 / 作业查询 / 认证 / 尺寸边界。
- `app/audio/orchestrator.py`：按序任务与持久化状态。
- `app/audio/worker.py`：单实例异步 Worker、自动恢复。
- `app/asr/real_provider.py`：真实语音服务适配器。
- `app/service.py`、`app/semantic/`、`app/db.py`：业务 Fact Engine、语义层与 SQLite。

### B. 本仓库公开评委 Demo（隔离测试环境）

`fitcore-judge-demo` 单容器组合：`web` → `proxy` → 独立 Core + SQLite。录音的测试 WAV 由 `fixtures/wav/` 提供，ASR 为 `core/fake_test_asr.py` 中的 **FAKE_TEST（音频哈希映射固定转录）**，语义 Provider 也为 fake。此路径使用真实 HTTP 与数据库 / 业务状态，但不连接真实 D3200、真实 ASR、真实 Nova。

已有交接证据：安全门禁 12/12；公开 Demo E2E 21/21；记录 60kg×8、Review 480kg·次。**这些不是 AI 音频识别准确率测试。**

## 3. iOS 代码结构与真实边界

`Dnlock/fitcore-ios` 公开仓库当前为私有访问；实际 Swift 工程主要在 `lhy/*` 与 `handoff/ios-training-api-debug-20261017` 等分支，不在其仅 4 个文件的 `main`：

| 文件 | 职责与边界 |
| --- | --- |
| `ios/Fitcore/Services/Soundcore/SoundcoreSDKRealSession.swift` | 官方 SDK 初始化、鉴权、扫描、连接真实调用；自身标明 Phase 1 不含音频传输 |
| `ios/Fitcore/Services/Soundcore/SoundcoreRecorderGateway.swift` | 连接状态与 SDK 回调映射；不是音频解码的完整验收 |
| `ios/Fitcore/Services/Soundcore/SoundcoreAudioBackend.swift` | 音频 SDK 适配占位；其 `isSDKAvailable` 在仓库该版本仍返回 false |
| `Support/AudioNormalization/SourceAudioDecoder.swift` | 格式检测与解码边界；该通用实现目前只对 PCM16 WAV 解码，Opus/AAC 返回 unsupported |
| `Support/AudioNormalization/WAVNormalizer.swift` | PCM16 WAV 标准化到 16kHz、单声道、16bit |
| `ios/Fitcore/Services/Audio/IPhoneMicrophoneBackend.swift` | iPhone 麦克风备选采集途径，AVAudioRecorder |
| `ios/Fitcore/Core/WAVHTTP/BackendHTTPClient.swift` | HTTPS Session / WAV Upload / Job / Facts / Finish / Review |
| `ios/Fitcore/Core/WAVHTTP/CloudTrainingModel.swift` | 客户端状态机，序号、幂等、事实与复盘展示 |
| `ios/Fitcore/Core/Configuration/TrainingAPIConfigurationStore.swift` | Debug Keychain 训练 API 配置，不与旧 `/v1/me` 云同步绑定 |

LHY 在本地 Mac 曾记录真实 D3200 连接、Opus 数据与解码 WAV 的阶段性结果；这些工作不一定已经完整推送至上述 GitHub 分支。因此不能只看仓库中的 Opus 占位就断言其本地完全没有解码能力，也不能用本地阶段报告断言整条同步链已经打通。

## 4. 当前阻断点与表达边界

1. D3200 真机稳定录音与可重放的原始音频证据需要最终复测。
2. iPhone 端的 D3200 音频 → WAV → 云端上传/授权 → 真实 ASR → Facts / Review 整链尚未得到统一 PASS。
3. 旧账户云同步 `/v1/me` 404 与 Debug 训练 API 的 HTTP 接线是不同问题，不能混淆。
4. 录音豆没有摄像头，也不能替代动作视觉分析；“动作纠正”或“实时语音指导”不应描述为已有。
5. 浏览器独立交互原型（例如 `mobile_final(8).html`）如果未接代理 / Core API，其页面记录仅是原型展示，不是设备或云端联调成功。

## 5. 数据保存、权限、迁移与安全

- 上游完整 WAV HTTP 实现会把音频作为 SQLite BLOB / 音频任务数据存储，训练事实与 Review 也由 SQLite 持久化；**当前没有可对外承诺的自动音频删除周期**。
- API 使用 Bearer 鉴权；评委代理只在服务端保存测试 Token，浏览器不得接触 API Token 或模型密钥。
- 来源验证：测试环境可用服务器侧 `AUDIO_TEST_SOURCE_TRUSTED` 开关；这**不等于真实声纹验证**。
- 迁移：将 SDK 采集层与 WAV + HTTPS API 解耦，使未来替换麦克风、Android 适配或不同 ASR Provider 成为可能；但设备 SDK、BLE 生命周期、权限、音频编解码仍需逐平台适配，不能声称零成本跨平台。

## 6. 比赛技术陈述建议

> Fitcore 采用硬件采集与 AI 业务解耦的架构。Soundcore 录音豆计划作为训练语音入口，iPhone 负责设备接入和音频格式标准化，云端以完整 WAV 的异步任务完成 ASR、训练语义理解、可信训练事实写入及复盘。当前云端 HTTP、真实 ASR 与训练事实链路已有单条音频验收；公开评委 Web 提供使用确定性测试 ASR 的可操作业务闭环。录音豆到 iPhone 再到云端的整体真机链路仍需最终验收。
