<div align="center">
  <img src="frontend/src/assets/qunxue-brand-mark.svg" alt="群学致知品牌标志" width="72" />
  <h1>群学致知</h1>
  <p><strong>从一个社会现象开始，走到一条可以核对的研究路径。</strong></p>
  <p>
    <a href="https://qunxue.xyz">在线体验</a>
    ·
    <a href="docs/product/README.md">产品事实</a>
    ·
    <a href="docs/onboarding.md">本地启动</a>
  </p>
</div>

---

群学致知是面向社会学入门者和初级研究者的理论发现与研究设计工作台。

它从一个真实的研究困惑、未完成的研究或已有理论框架开始，帮助用户梳理现象、比较解释、回到知识来源并形成下一步研究计划。系统负责展开选择和保留证据线索，最终的理论判断与研究责任仍然属于研究者。

## 在线产品

当前线上入口：**[qunxue.xyz](https://qunxue.xyz)**

产品首页展示从研究现象到研究路径的完整入口；登录后进入工作台，可以继续已有研究、创建新研究、与研究 Agent 对话、浏览知识库和探索知识图谱。

## 一条连续的研究路径

| 阶段 | 研究者在这里完成什么 |
| --- | --- |
| 现象 | 从困惑或材料开始，整理研究对象、范围和变化，并确认现象表述。 |
| Agent | 让 Agent 追问对象、机制、证据与未知，而不是直接替研究者下结论。 |
| 知识 | 浏览版本化理论条目、来源和知识图谱，回到可以核对的内容。 |
| 判断 | 并置候选理论的解释重点、适用前提、差异和证据缺口，由研究者作出选择。 |
| 框架 | 将已确认的判断整理为研究问题、概念关系、方法、材料计划和待核对事项。 |

研究 Agent 可以根据问题调用知识工具；工具结果、来源版本和研究文档状态会保留在工作流中，便于继续核对。模型输出是研究建议，不自动成为正式结论。

## 主要空间

- **工作台**：继续正在形成的研究，查看研究状态和下一步。
- **研究 Agent**：围绕社会学研究问题进行多轮对话，保留上下文、证据和可继续的动作。
- **新建研究**：从具体现象、已有理论或研究材料进入研究流程。
- **知识库**：搜索和阅读版本化的社会学理论知识，查看条目来源与相关关系。
- **知识图谱**：从理论位置与关系出发探索知识目录，并回到具体条目核对。
- **研究工作台**：在理论判断和正式研究框架中保留选择、审阅、修订与版本历史。

## 当前边界

README 描述的是当前线上产品主线；运行能力以已合入 `main` 的代码、测试和实际环境为准。

- 最终理论选择、研究问题和学术判断由用户完成，系统不替用户承担结论责任。
- 本地零配置启动使用确定性 Mock；健康检查、页面渲染或类型契约不能单独证明真实模型已接通。
- 真实模型、检索服务、知识发布版本和引用链需要结合部署环境逐项核验，不能仅凭配置名推断。
- 本地 SQLite 适用于单实例、单 worker 的开发与内网演示；公网部署还需要独立完成 TLS、反向代理、数据库、密钥、备份、监控和审计。

## 技术栈

- **Web**：React、TypeScript、Vite、TanStack Query
- **API**：FastAPI、Pydantic
- **数据**：SQLAlchemy、Alembic、SQLite
- **契约**：OpenAPI、Hey API 生成的 TypeScript SDK
- **检查**：uv、npm、Ruff、Vitest、Oxlint

## 五分钟启动

需要 Git、GNU Make、Python 3.12、[uv](https://docs.astral.sh/uv/)、Node.js 22.18+、npm 和 [GitHub CLI](https://cli.github.com/)。

```bash
git clone https://github.com/huyanxius/qunxue.git
cd qunxue
make bootstrap
```

分别启动 API 和 Web：

```bash
make dev-api
make dev-web
```

浏览器打开 <http://localhost:5173>。默认本地运行不需要 API key；完整环境变量、冒烟流程和真实 Provider 配置见 [`docs/onboarding.md`](docs/onboarding.md)。

## 检查

```bash
make check
```

这会执行契约生成与漂移检查、后端 lint/测试、前端模块边界检查、lint、类型检查、测试和生产构建。

## 仓库入口

- [`docs/product/README.md`](docs/product/README.md)：产品定位、竞赛边界、证据和待决问题。
- [`docs/onboarding.md`](docs/onboarding.md)：开发环境、启动方式和本地冒烟流程。
- [`docs/DISTRIBUTION.md`](docs/DISTRIBUTION.md)：分发、运行、备份与发布边界。
- [`docs/SECURITY.md`](docs/SECURITY.md)：密钥、数据、部署和安全边界。
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)：模块职责、依赖方向和接口边界。
- [`CHANGELOG.md`](CHANGELOG.md)：工程变更记录。
- [`CONTRIBUTING.md`](CONTRIBUTING.md)：Issue、分支、提交和 PR 流程。

## 协作约束

所有改动都通过 `Issue → 分支 → 原子提交 → PR → main` 交付，不直接推送 `main`。密钥、数据库文件、依赖目录、截图和构建产物不进入仓库；涉及 API 的改动必须通过契约生成流程更新客户端。
