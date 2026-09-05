# 工作区设计令牌（待验收草稿）

本次设置 UI 尚未通过用户视觉验收。已核对的现有令牌值可作事实依据；字体角色与设置页应用仍需按用户指定的基准页面校正，不作为已接受的全站规范。

设置、研究、材料与记忆页面使用同一套语义令牌。数值定义在 `frontend/src/styles/tokens.css`，产品外壳的颜色通过 `frontend/src/styles/app.css` 中 `.app-frame` 映射，Tailwind 在 `theme.css` 暴露对应工具类。新页面不能仅导入 tokens.css 就宣称与产品对齐：必须处于相同的外壳颜色作用域，并选择正确的字体与圆角角色。

| 角色 | 令牌 | 用法 |
| --- | --- | --- |
| 页面题目 | `--qx-text-section--font-family` / `--qx-text-workspace-title` | 宋体；研究主题、设置分区题目、确认弹层标题 |
| 用户名、首字头像 | `--qx-font-ui` | UI 字体；身份信息不使用宋体 |
| 阅读文本 | `--qx-font-reading` | 宋体；文稿与长篇研究内容 |
| 导航、字段、按钮、状态 | `--qx-font-ui` | 无衬线 UI 字体；不能因标题用宋体就把所有字段都换成宋体 |
| 小型导航与工具 | `--qx-radius-compact` | 8px；紧凑工具与设置导航的圆角矩形选中态 |
| 输入框、搜索框 | `--qx-radius-control` | 12px |
| 普通内容表面 | `--qx-radius-surface` | 16px；材料卡片、记忆详情 |
| 完整任务浮层 | `--qx-radius-feature` | 24px；账户设置等完整浮层，收回 theme.css 原有 feature 值 |
| 操作按钮、头像、开关 | `--qx-radius-pill` | 胶囊或正圆；与研究页主操作保持一致 |
| 灰阶 | `--qx-color-*` | 从产品外壳继承；禁止每个页面自行调一套近似灰 |
| 排版与留白 | `--qx-text-*` / `--qx-space-*` | 字号连同行高、字重使用；分组用留白，分隔线只分隔有意义的内容组 |

## 当前页面依据

用户指定「研究 Agent」与「我的研究」；example 是“例如”，不是页面名。

- `research-materials-page.css`：研究题目用宋体，搜索框使用 control，主操作用 pill，项目卡片用 surface。
- `research-agent-conversation.css`：当前 `/agent` 路由的研究正文与研究标题用宋体，工具及状态用 UI 字体；不以旧版 `research-agent-page.css` 为依据。
- 「我的研究」对应 `/research/materials`：项目主标题宋体 26px / 1.4 / 550，卡片标题 UI 15px；主操作高 42px、文字 13px、胶囊圆角，搜索框圆角 12px。
- `app.css`：侧栏首字头像 40px、UI 15px / 500、浅色底。身份信息不套研究题目的字体。
- `theme.css`：原本已有 24px feature 档，新增的 `--qx-radius-feature` 将它纳入 `--qx-*` 唯一命名体系，原有取值不变。

## 设置页的应用

账户摘要强调姓名与首字头像；字段名和字段值相邻，右侧只放操作。积分页突出余额和实际账目；安全页区分密码与设备；危险操作使用独立的危险色和确认弹层。各分区根据内容组织，不能全部复制同一种空表单。

保留既有 API 和业务状态机，重写 UI。无头像上传与主题持久化接口的功能不加入。研究通知目前只有偏好持久化、没有发送链路，因此删除其界面开关。预览只注入示例数据，不代表已验证生产服务。

## 外部参照

- [Linear 2026 界面改版](https://linear.app/now/behind-the-latest-design-refresh)：降低导航权重，使主要内容突出，减少无意义的边界线。
- [Linear 设置重构](https://linear.app/changelog/2024-12-18-personalized-sidebar)：按账户、功能、管理范围划分设置，用概览进入细项。
- [Notion 账户设置](https://www.notion.com/help/account-settings)：资料、偏好、账户安全保持明确的用户语义。
- 用户提供的 Perplexity 与文枢设置参照：双栏浮层、分组内容、字段与操作分离；不照搬它们独有的业务能力。
