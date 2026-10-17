# GitHub 仓库与分支说明（2026-10-17）

| 仓库 | GitHub main 状态 | 有效分支 / 内容 | 比赛提交建议 |
| --- | --- | --- | --- |
| `Dnlock/fitcore-judge-demo` | 公共评委 Demo，固定 `03667ff` | Web + Proxy + 隔离 Core + FAKE_TEST + E2E | 官方源代码链接的首选；先审查敏感信息 |
| `Dnlock/fitcore-judge-demo-ui-preview` | 独立 UI 重构 `2e13a281` | 预览版，设计对齐、jsdom/本地 E2E；真实浏览器截图验收未完成 | 不要冒充正式部署 |
| `Dnlock/fitcore-ios` | main `4f27908f` 极简基线 | `lhy/soundcore-local-link`、`lhy/fitcore-ios-real-integration-20261017`、`handoff/ios-training-api-debug-20261017` | 仅在明确允许公开 SDK 适配源代码并完成脱敏审查后再补充 |
| `Dnlock/fitcore-core` | main `bc264f0` 旧稳定版 | `feature/wav-http`、`trae/core-after-r7-20261015`、`integration/fitcore-v2-algorithm-backend-20261017` | 看源码与验收时必须标注 branch/SHA |
| `Dnlock/fitcore-agent-sync` | 团队内部协调 | 历史验收与进度，不能替代代码审查 | 不建议作为赛事提交主仓库 |

注意：
- GitHub 分支的文件存在，不等于 iOS 真机全部运行成功，也不等于这些分支已合并到 main / 已部署生产。
- 公开评委演示的固定测试 Provider 与真实音频模型是两条不同链路；不得混用其测试数字。
- 两个 public 仓库暂未经过本次整理后的**全 Git 历史敏感信息扫描**；正式提交者需复核历史、日志、fixtures 的音频性质以及 SDK 授权范围。
- 源码不包含真实凭据、设备 SDK 完整源代码、原始私人录音；如果后续安全审查发现异常，应停止公开分发并立即处理，而非仅删除工作树文件。
