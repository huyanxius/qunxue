# 前端设计系统统一 实施计划

> **给执行者：** 每一步都是可单独提交的动作。按顺序做，不要跳步，不要把多个阶段挤进一个提交。
> 复选框 `- [ ]` 用来标记进度。

**目标：** 让整个前端只存在一套设计令牌和一套基础控件，页面样式表只管布局，不再各自定义控件长什么样。

**架构：** 引入 Tailwind v4，把设计令牌搬进它的 `@theme` 块——值只存在于这一处，页面里写不出 `font-size: 9px` 这种东西，想要新值必须回去补令牌。现有 CSS 与 Tailwind 共存，一页一页迁移，迁完就删掉那一页的样式表。最后加一个检查脚本挡住复发。

**技术栈：** Tailwind v4（`@tailwindcss/vite`）、Vite 8、React 19、Vitest 4、oxlint。

---

## 为什么要做这件事

现状是十四个样式表各带一套自己的局部调色板（`--materials-*`、`--research-shell-*`、`--research-*`、`--rdw-*`、`--app-*`……），三十五个样式表约两万一千行，按钮、卡片、输入框在六个以上文件里各写各的（光 `button {` 规则最多的一个文件写了二十二遍）。

后果是可验证的，不是审美偏好：

- 改 `styles/tokens.css` 常常看不到变化，因为 `.app-frame` 就地覆盖了 `--bg` / `--ink` / `--radius` 这些同名变量，同一个变量名在外壳内外解析出两种值。
- 同一档字在不同面板里行高不一（材料库 1.4、档案面板 1.55），因为令牌只给了字号没给行高，行高被推给每个组件各自发明。
- 缺状态色语义位，组件就地写死颜色：档案与质性面板里曾有 `#9c7a31` / `#806522` / `#d4bd76` 一族暖棕，跟全站冷灰不是同一批颜色。
- 全库曾有约 460 处写死的 `font-size: Npx`，其中八成在 8–10px。

Tailwind 在这里不是"跟风"，是**强制机制**：值只存在于 `@theme`，页面拿不到就得回去补，靠机制而不是靠纪律。同一套词汇也和 Windup 对齐，评审时不用来回翻译。

---

## 前置条件（必须先完成）

分支 `refactor/200-materials-reading-workspace` 上有九个已完成并验证过的提交，**必须先合入 main**，否则这份计划的每个阶段都会跟它冲突。它已经做完的事，不要重做：

```
a32ff63 refactor(research-materials): 模块样式收进令牌
ae69299 refactor(tokens): 按 Windup 的结构重做令牌层，色相不变
ff10cde refactor(research-workspace): 顶栏收成一行，与文档栏合成同一块 chrome
2de9d00 fix(research-materials): 定位符改用段内预留槽，收起侧栏后不再压住正文
7c2141e fix(research-materials): 按真实渲染修正窄栏排版
ce535a3 test(research-materials): 跟进材料库与阅读台的结构变化
1a53c58 refactor(research-analysis): 把分析独立成中心工具而非材料工具的一种模式
0b165b6 refactor(research-materials): 拆分材料库、阅读台与片段标记抽屉
94bbf0c refactor(tokens): 补齐 qx 语义令牌层并在应用外壳内对齐取值
```

具体已经落地的：`styles/tokens.css` 已重写成带配套行高的字阶、三档语义圆角、按角色分档的阴影、补齐 soft/line 变体的状态色；材料工具已拆成材料库 / 阅读台 / 标记抽屉 / 档案抽屉四块，分析已独立成 `ResearchAnalysisPanel`；`research-materials.css` 里 111 处写死字号、9 处色值、20 处圆角已归位。

---

## 验证基线（重要）

下面五个用例在**干净的 main 上就是失败的**，是 Node 环境的 FormData/File 断言问题，不是你弄坏的。看到它们失败请忽略，看到别的失败才是回归：

```
src/app/agent/NewResearchWorkspacePage.test.tsx > creates no empty task on open and keeps first materials on one draft task
src/app/research/ExistingResearchEntryPage.test.tsx > creates one project and uploads every selected initial material into it
src/modules/research-exchange/researchExchangeApi.test.ts > uses the generated client for audit, archive export, and QDPX preview
src/modules/research-materials/professionalMaterialsApi.test.ts > keeps every file result from a 207 batch upload
src/modules/research-materials/researchMaterialsApi.test.ts > uploads a supported file as multipart data with its research kind
```

每个阶段结束时跑这四条，全部在 `frontend/` 目录下执行：

```bash
npx tsc -b --pretty false          # 期望：无输出
npx vitest run                     # 期望：仅上述 5 个失败
npx oxlint                         # 期望：只有既有 warning，无 error
npm run check:boundaries           # 期望：Module boundaries: ok
```

---

## 三条红线

1. **改名不改值。** 塌缩局部调色板时，新值必须逐个等于旧值。改名时顺手换色，会把没人碰过的页面整体重新皮肤化——看上去就像同一个产品里混进了半成品。调色是独立的设计决定，要连着受影响的页面一起重做，不能搭迁移的车。
2. **迁移不改设计。** 一页迁完的判定标准是"看起来跟迁移前一模一样"，不是"看起来更好了"。想改设计另开提交。
3. **每页迁完必须在浏览器里看过。** 跑通测试不等于渲染正确。启动方式：

```bash
cd frontend && NO_PROXY=127.0.0.1,localhost VITE_API_PROXY_TARGET=http://127.0.0.1:8001 npx vite --host 127.0.0.1 --port 5174
```

---

## 文件结构

**新建：**
- `frontend/src/styles/theme.css` — Tailwind 入口与 `@theme` 令牌块，全站唯一的取值来源
- `frontend/src/shared/ui/control-classes.ts` — 基础控件的类名常量，全站唯一的控件定义
- `frontend/scripts/check-style-tokens.mjs` — 防复发检查

**改造：**
- `frontend/vite.config.ts` — 挂 Tailwind 插件
- `frontend/src/main.tsx` — 引入 `theme.css`
- `frontend/src/styles/tokens.css` — 退化成兼容别名层，指向 `@theme`
- `frontend/src/styles/app.css` — 删掉 `--app-*` 私有调色板
- 其余 32 个样式表 — 逐个塌缩调色板、逐页迁移后删除

---

## 阶段一：装 Tailwind，令牌进 @theme

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/vite.config.ts`
- Create: `frontend/src/styles/theme.css`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/styles/tokens.css`

- [ ] **Step 1: 装依赖**

```bash
cd frontend
npm i -D tailwindcss@^4.3.3 @tailwindcss/vite@^4.3.3
```

版本跟 Windup 对齐（`Windup/frontend/package.json` 里是 `^4.3.3`）。

- [ ] **Step 2: 挂插件**

改 `frontend/vite.config.ts`，只动 import 和 plugins 两行：

```ts
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': process.env.VITE_API_PROXY_TARGET ?? 'http://127.0.0.1:8000',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
  },
})
```

- [ ] **Step 3: 建 `frontend/src/styles/theme.css`**

Tailwind v4 的 `@theme` 用带命名空间的变量名（`--color-*` / `--text-*` / `--radius-*` / `--shadow-*` / `--font-*`），才会生成对应的工具类。取值逐个照抄现在的 `tokens.css`，一个都不许改。

```css
@import 'tailwindcss';

/*
 * 全站唯一的取值来源。页面拿不到某个值，说明这里还没有——回来补，不要在页面里就地写死。
 *
 * 字阶每一档连着自己的行高、字距、字重一起给：只给字号等于把行高推给每个组件各自发明，
 * 同一档字在不同面板里高矮不一，这是界面看着像毛坯的直接原因。
 * 中文行高不低于 1.45——中文字面几乎占满 em box，压到 1.2 相邻行的墨迹会真的贴上。
 */
@theme {
  /* 表面：从最底的画布到浮起的纸面 */
  --color-canvas: #f5f5f5;
  --color-surface: #ffffff;
  --color-surface-raised: #ffffff;
  --color-surface-muted: #f7f7f7;
  --color-surface-strong: #ededed;

  /* 墨色：ink 标题，ink-soft 正文，muted 元信息，faint 几乎不看的定位符 */
  --color-ink: #111111;
  --color-ink-soft: #303030;
  --color-muted: #6c6c6c;
  --color-faint: #969696;

  --color-rule: #e3e3e3;
  --color-rule-strong: #cccccc;

  /* 强调色就是墨黑：层级靠字号、留白和分隔线拉开，不靠彩色 */
  --color-accent: #111111;
  --color-accent-hover: #303030;
  --color-accent-soft: #ececec;
  --color-accent-muted: #f4f4f4;
  --color-on-accent: #ffffff;

  /* 状态色只有 danger 是彩的；notice 是"读一下就好"，走中性灰加一道左线 */
  --color-danger: #98434b;
  --color-danger-line: #d8b3b7;
  --color-danger-soft: #f8edef;
  --color-notice: #303030;
  --color-notice-line: #b8b8b8;
  --color-notice-soft: #f2f2f2;

  --font-ui: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
  --font-reading: 'Songti SC', 'Noto Serif CJK SC', Georgia, serif;

  /* 字阶，比例约 1.25 */
  --text-section: 1.5rem;
  --text-section--line-height: 1.3;
  --text-section--letter-spacing: -0.025em;
  --text-section--font-weight: 580;

  --text-title: 1.125rem;
  --text-title--line-height: 1.45;
  --text-title--letter-spacing: -0.02em;
  --text-title--font-weight: 580;

  --text-heading: 0.9375rem;
  --text-heading--line-height: 1.5;
  --text-heading--font-weight: 600;

  /* 只给宋体原文用，行高比界面正文更松 */
  --text-reading: 1rem;
  --text-reading--line-height: 1.9;

  --text-body: 0.9375rem;
  --text-body--line-height: 1.6;

  --text-meta: 0.75rem;
  --text-meta--line-height: 1.5;

  /* 领读词，字距拉开才不像正文的一部分 */
  --text-eyebrow: 0.6875rem;
  --text-eyebrow--line-height: 1.45;
  --text-eyebrow--letter-spacing: 0.11em;
  --text-eyebrow--font-weight: 600;

  /* 引用坐标，字阶的地板，再小就只剩装饰用途 */
  --text-locator: 0.6875rem;
  --text-locator--line-height: 1.45;

  /* 圆角三档逐级放大：紧凑元素、交互控件、内容表面。胶囊另用 rounded-full。
     三档之外不要临时插值——一插就没人知道该用哪个了。 */
  --radius-compact: 8px;
  --radius-control: 12px;
  --radius-surface: 16px;

  /* 阴影按角色：卡片浮一点，面板和抽屉浮多一点，菜单短促，拖拽物最高 */
  --shadow-card: 0 18px 45px rgb(17 17 17 / 8%);
  --shadow-panel: 0 22px 60px rgb(17 17 17 / 10%);
  --shadow-menu: 0 8px 24px rgb(17 17 17 / 9%);
  --shadow-float: 0 16px 40px rgb(17 17 17 / 18%);
}
```

- [ ] **Step 4: 在 `frontend/src/main.tsx` 里最先引入 theme.css**

打开 `frontend/src/main.tsx`，把 `theme.css` 加在所有其它样式引入之前（它要先建立层级，后面的普通 CSS 才能盖住它）：

```ts
import './styles/theme.css'
import './styles/tokens.css'
import './styles/base.css'
import './styles/app.css'
```

如果 `main.tsx` 现在的引入顺序不是这样，保持原有顺序，只把 `./styles/theme.css` 插到最前面。

- [ ] **Step 5: 把 `tokens.css` 退化成别名层**

`tokens.css` 里所有 `--qx-*` 的字面取值改成指向 `@theme` 的变量，删掉重复的值定义。示例（整个文件按这个模式改）：

```css
:root {
  --qx-color-canvas: var(--color-canvas);
  --qx-color-surface: var(--color-surface);
  --qx-color-ink: var(--color-ink);
  --qx-text-body: var(--text-body);
  --qx-text-body--line-height: var(--text-body--line-height);
  --qx-radius-control: var(--radius-control);
  --qx-shadow-card: var(--shadow-card);
  /* ……其余同理，一一对应，不新增也不删减 */
}
```

保留文件末尾那组短名别名（`--bg`、`--ink`、`--radius` 等），它们还有几十个老模块在用。

- [ ] **Step 6: 验证没有任何视觉变化**

```bash
npx tsc -b --pretty false
npx vitest run
```

然后起开发服务器，在浏览器里逐个打开这三条路径，跟改动前对比截图，**必须一模一样**：

```
/app
/research/<任一项目id>/workspace/materials
/research/<任一项目id>/workspace/map
```

- [ ] **Step 7: 提交**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts \
        frontend/src/styles/theme.css frontend/src/main.tsx frontend/src/styles/tokens.css
git commit -m "build(frontend): 引入 Tailwind v4，设计令牌收进 @theme

值全部照抄现有 tokens.css，一个没改；tokens.css 退化成指向 @theme 的别名层，
老模块继续可用。这一步不改任何观感。"
```

---

## 阶段二：塌缩十四套局部调色板

每个文件一个提交。**只改名不改值**，改完对着改动前的截图逐个确认无变化。

按下面顺序做（从简单到复杂，先在小文件上把手法练熟）：

| 顺序 | 文件 | 局部变量数 |
| --- | --- | --- |
| 1 | `app/research/existing-research-entry.css` | 4 |
| 2 | `app/research-workspace/research-context-rail.css` | 4 |
| 3 | `app/research-workspace/research-project-workspace.css` | 4 |
| 4 | `app/home/app-home.css` | 4 |
| 5 | `modules/research-materials/research-materials.css` | 4 |
| 6 | `app/research-workspace/research-document-workbench.css` | 5 |
| 7 | `app/agent/new-research-workspace.css` | 6 |
| 8 | `modules/knowledge-explorer/knowledge-preview.css` | 6 |
| 9 | `app/research-workspace/research-map-canvas.css` | 7 |
| 10 | `app/agent/research-agent-conversation.css` | 10 |
| 11 | `modules/account/account-management.css` | 20 |
| 12 | `app/foundation/foundation.css` | 22 |
| 13 | `modules/knowledge-explorer/knowledge-ui.css` | 36 |
| 14 | `styles/app.css` | 53 |

- [ ] **Step 1: 打开文件，找到局部调色板定义**

以第 3 个 `research-project-workspace.css` 为例，它顶上是：

```css
.research-project-workspace {
  --research-shell-ink: #252823;
  --research-shell-muted: #6f756e;
  --research-shell-line: #d9ddd7;
  --research-shell-paper: #f8f9f6;
```

- [ ] **Step 2: 逐个换成 @theme 里最接近的角色，值必须相等或极接近**

```css
.research-project-workspace {
  /* 工作区外壳原本自带一组带绿的灰，跟全站冷灰不是同一批颜色，两条栏叠在一起
     能明显看出是两种材质。改成同一套语义令牌。 */
  --research-shell-ink: var(--color-ink);
  --research-shell-muted: var(--color-muted);
  --research-shell-line: var(--color-rule);
  --research-shell-paper: var(--color-surface-muted);
```

选角色的依据：最深的墨 → `--color-ink`；次级文字 → `--color-ink-soft`；元信息 → `--color-muted`；几乎不看的 → `--color-faint`；细线 → `--color-rule`；重线 → `--color-rule-strong`；页面底色 → `--color-canvas`；浮起的纸面 → `--color-surface-raised`；分区底色 → `--color-surface-muted`。

- [ ] **Step 3: 顺手把这个文件里写死的字号、圆角、色值也换掉**

同一个文件只碰一次，不要为了"纯改名"分两轮。映射规则：

- `font-size: 8px` / `9px` → `var(--text-locator)`，并在同一条规则里补 `line-height: var(--text-locator--line-height)`
- `font-size: 10px` / `11px` / `12px` → `var(--text-meta)` + 配套行高
- `font-size: 13px` / `14px` / `15px` → `var(--text-body)` + 配套行高
- `font-size: 16px` → `var(--text-reading)` + 配套行高
- `font-size: 18px` / `19px` → `var(--text-title)` + 配套行高
- `font-size: 24px` / `25px` → `var(--text-section)` + 配套行高
- `border-radius: 4px`–`8px` → `var(--radius-compact)`
- `border-radius: 9px`–`12px` → `var(--radius-control)`
- `border-radius: 13px`–`24px` → `var(--radius-surface)`
- `border-radius: 999px` / `50%` → 保持不动（胶囊和正圆）
- 中性灰 hex → 按 Step 2 的角色表
- 暖棕一族（`#9c7a31` `#806522` `#a56b2a` `#8a6c38` `#65451d` `#d4bd76` `#e4b976`）→ `--color-notice` 系（文字用 `--color-notice`，左线用 `--color-notice-line`，底色用 `--color-notice-soft`）
- 红棕一族（`#824a3d` `#8f4939` `#b96043`）→ `--color-danger` 系

**例外，不要动：** `modules/knowledge-graph/*.css` 里的节点配色（`#3e7cb1` 等）是数据编码不是界面色，保持原样。

- [ ] **Step 4: 验证**

```bash
npx tsc -b --pretty false && npx vitest run
```

浏览器里打开这个文件对应的页面，跟改动前截图对比，必须一模一样。

- [ ] **Step 5: 提交（每个文件一个提交）**

```bash
git add frontend/src/app/research-workspace/research-project-workspace.css
git commit -m "refactor(research-workspace): 外壳调色板塌缩成语义令牌

改名不改值，观感无变化。"
```

- [ ] **Step 6: 回到 Step 1，做表格里的下一个文件**

---

## 阶段三：共享基础件

**Files:**
- Create: `frontend/src/shared/ui/control-classes.ts`
- Modify: `frontend/src/modules/research-materials/MaterialLibraryView.tsx`
- Modify: `frontend/src/modules/research-materials/MaterialReaderView.tsx`
- Modify: `frontend/src/modules/research-materials/MaterialAnnotationDrawer.tsx`
- Modify: `frontend/src/modules/research-materials/ResearchAnalysisPanel.tsx`
- Modify: `frontend/src/app/agent/ResearchAgentConversationPage.tsx`
- Modify: `frontend/src/modules/research-materials/research-materials.css`（删掉被替换掉的规则）

- [ ] **Step 1: 建 `frontend/src/shared/ui/control-classes.ts`**

照 Windup `shared/ui/product-control.ts` 的做法：控件不做成组件，做成类名常量，页面直接拼。这样不引入一层组件抽象，但定义只有一处。

```ts
/**
 * 全站基础控件的类名。控件长什么样只在这里定义一次；页面样式表只管布局。
 *
 * 不做成 React 组件是有意的：组件会引入一层 props 抽象，而这些控件的差异只在类名上。
 * 需要变体时在这里加一个常量，不要在页面里拼 `${buttonClass} rounded-none` 这种覆盖——
 * 那等于又开始各写各的。
 */

export const buttonClass =
  'inline-flex flex-none items-center justify-center gap-2 h-9 px-4 rounded-control border border-rule-strong bg-surface text-body text-ink whitespace-nowrap transition-colors hover:border-ink disabled:cursor-not-allowed disabled:opacity-45'

export const buttonPrimaryClass =
  'inline-flex flex-none items-center justify-center gap-2 h-9 px-4 rounded-control border border-accent bg-accent text-body font-semibold text-on-accent whitespace-nowrap transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-45'

export const iconButtonClass =
  'grid size-8 place-items-center rounded-control text-muted transition-colors hover:bg-surface-muted hover:text-ink aria-pressed:bg-surface-strong aria-pressed:text-ink'

/** 内容表面：卡片、抽屉、弹层共用。悬停抬边框而不是加深底色，列表才不会一片闪。 */
export const cardClass =
  'rounded-surface border border-rule bg-surface-raised transition-[border-color,box-shadow] hover:border-rule-strong hover:shadow-card focus-within:border-accent focus-within:shadow-card'

export const panelClass =
  'rounded-surface border border-rule-strong bg-surface-raised shadow-panel'

export const fieldLabelClass = 'flex items-baseline gap-2 text-meta font-semibold text-ink'

export const fieldInputClass =
  'w-full min-w-0 rounded-control border border-rule bg-surface px-3 py-2 text-body text-ink outline-none focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent'

/**
 * 提示条只有三种语气，不要再加第四种。
 * notice 是"读一下就好"，走中性灰；danger 是"这件事没成"；success 是"成了"。
 * 三者结构一致——一道左线加一块浅底——语气只由颜色区分，不靠边框粗细或圆角变化。
 */
const calloutBase = 'flex items-start gap-2 rounded-control border-l-2 px-3 py-2 text-meta'

export const calloutClass = {
  notice: `${calloutBase} border-l-notice-line bg-notice-soft text-ink-soft`,
  danger: `${calloutBase} border-l-danger bg-danger-soft text-danger`,
  success: `${calloutBase} border-l-accent bg-accent-soft text-ink`,
} as const

export type CalloutTone = keyof typeof calloutClass

/**
 * 页面标题块：标题加一行支撑信息，两行封顶。
 * 不要再加眉标——顶栏已经写着当前在哪个项目，「当前研究」这类领读词是给标题找由头。
 */
export const pageTitleClass = 'font-reading text-section text-ink'
export const pageSummaryClass = 'text-body text-muted'
```

- [ ] **Step 2: 换掉材料库的行卡片与按钮**

打开 `MaterialLibraryView.tsx`，把 `className="qx-button qx-button--primary"` 换成 `className={buttonPrimaryClass}`，`className="qx-library__row"` 换成 `className={\`flex items-center gap-2 ${cardClass}\`}`，并在文件顶部引入：

```ts
import { buttonPrimaryClass, cardClass, pageSummaryClass, pageTitleClass } from '../../shared/ui/control-classes'
```

同时把页头那三行压成两行——去掉 `<span className="qx-eyebrow">当前研究</span>`，标题用 `pageTitleClass`，摘要行用 `pageSummaryClass`（从 12px 提到正文档，24 → 15 的落差比 24 → 12 → 11 稳）。

- [ ] **Step 3: 删掉 `research-materials.css` 里被替换掉的规则**

删除这些选择器及其规则体：`.qx-button`、`.qx-button--primary`、`.qx-icon-button`、`.qx-message`、`.qx-field`、`.qx-field__label`、`.qx-eyebrow`、`.qx-library__row`、`.qx-library__open` 里的表面相关声明。布局相关的（`display`、`gap`、`grid-template-*`）留着。

- [ ] **Step 4: 换掉三处各写各的警示条**

现在有三份独立实现，全部换成 `calloutClass`：

- `research-materials.css` 的 `.professional-archive__guardrail`（档案里那条「当前材料仍可人工阅读」）→ `calloutClass.notice`
- `research-agent-conversation.css` 里 Agent 栏的中断提示 → `calloutClass.notice`
- 同文件里的 Agent 失败提示 → `calloutClass.danger`

- [ ] **Step 5: 验证**

```bash
npx tsc -b --pretty false && npx vitest run && npx oxlint
```

浏览器里走一遍：材料库 → 打开一份材料 → 划选一句原文出标记抽屉 → 保存 → 打开材料档案抽屉 → 切到分析页。每一屏都要跟迁移前一致。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/shared/ui/control-classes.ts frontend/src/modules/research-materials frontend/src/app/agent/ResearchAgentConversationPage.tsx
git commit -m "refactor(shared): 抽出全站基础控件类名，材料与 Agent 栏改用

按钮、图标按钮、卡片、字段、提示条只在 shared/ui/control-classes.ts 定义一次。
三处各写各的警示条统一成 notice / danger / success 三种语气。"
```

---

## 阶段四：逐页迁移

阶段三之后，剩下的样式表按同一套手法一页一页换。**这不是占位说明，下面就是完整做法**，每个文件重复即可。

按这个顺序（先小后大，先独立后共用）：

```
modules/research-exchange/research-exchange.css        162 行
app/research/research-materials-page.css                39 行
modules/account/recent-research.css                    187 行
modules/account/my-research.css                        325 行
app/research-workspace/research-context-rail.css        96 行
modules/research-method/research-method.css            196 行
modules/m4-theory-judgment/m4-theory-judgment.css      262 行
modules/socio-match-workspace/workspace.css            318 行
modules/knowledge-explorer/knowledge-library.css       869 行
modules/knowledge-explorer/knowledge-reader.css        801 行
app/agent/new-research-workspace.css                   875 行
modules/account/account-management.css                1873 行
app/agent/research-agent-conversation.css             1284 行
app/agent/research-agent-page.css                     1328 行
app/foundation/foundation.css                         4348 行
```

对每一个文件：

- [ ] **Step 1: 迁移前截图**

打开这个样式表对应的页面，截图存到 `docs/screenshots/migration/<文件名>-before.png`。这是唯一的验收依据。

- [ ] **Step 2: 把控件类规则换成基础件**

在对应的 `.tsx` 里，凡是套用了自制按钮、卡片、输入框、提示条的元素，改成引用 `control-classes.ts` 的常量。

- [ ] **Step 3: 把布局类规则换成 Tailwind 工具类**

`display: flex; gap: 12px; align-items: center` → `className="flex items-center gap-3"`。间距一律用 Tailwind 的 4px 刻度（`gap-2` = 8px、`gap-3` = 12px、`gap-4` = 16px、`gap-6` = 24px），不要用任意值 `gap-[13px]`。

- [ ] **Step 4: 删掉这个样式表**

整个文件删掉，并删掉引用它的 `import './xxx.css'`。如果还剩下确实无法用工具类表达的规则（keyframes、`::selection`、复杂选择器），把这几条挪进 `styles/app.css`，其余全删。

- [ ] **Step 5: 验证**

```bash
npx tsc -b --pretty false && npx vitest run && npx oxlint && npm run check:boundaries
```

再截一张 after 图，跟 before 逐像素对比。**不一致就是没迁完，不是"顺手改好了"。**

- [ ] **Step 6: 提交（每个文件一个提交）**

```bash
git add -A
git commit -m "refactor(<模块名>): 迁到 Tailwind 并删除自有样式表

布局改工具类，控件改共享基础件，观感不变。"
```

---

## 阶段五：防复发

**Files:**
- Create: `frontend/scripts/check-style-tokens.mjs`
- Modify: `frontend/package.json`

- [ ] **Step 1: 建检查脚本**

```js
// frontend/scripts/check-style-tokens.mjs
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

/*
 * 挡住"各自为政"复发：styles/ 之外的样式表不许出现裸的像素字号和裸的十六进制色值。
 * 想要新值就去 styles/theme.css 补令牌——这条约束是这整套设计系统唯一的强制机制，
 * 去掉它，半年后又会长回十四套局部调色板。
 */
const ROOT = new URL('../src', import.meta.url).pathname
const ALLOWED_DIRS = ['styles']
const ALLOWED_FILES = [
  // 知识图谱的节点配色是数据编码不是界面色，按维度区分必须用具体颜色。
  'modules/knowledge-graph/KnowledgeGraph.css',
  'modules/knowledge-graph/FullscreenKnowledgeGraph.css',
  'modules/knowledge-graph/ObsidianKnowledgeGraph.css',
]

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name)
    return statSync(full).isDirectory() ? walk(full) : full.endsWith('.css') ? [full] : []
  })
}

const failures = []
for (const file of walk(ROOT)) {
  const rel = relative(ROOT, file)
  if (ALLOWED_DIRS.includes(rel.split('/')[0])) continue
  if (ALLOWED_FILES.includes(rel)) continue
  const lines = readFileSync(file, 'utf8').split('\n')
  lines.forEach((line, index) => {
    if (/font-size:\s*\d/.test(line)) failures.push(`${rel}:${index + 1} 裸字号：${line.trim()}`)
    if (/#[0-9a-fA-F]{3,8}\b/.test(line)) failures.push(`${rel}:${index + 1} 裸色值：${line.trim()}`)
  })
}

if (failures.length) {
  console.error(`发现 ${failures.length} 处应当走令牌的取值：\n`)
  for (const failure of failures) console.error('  ' + failure)
  console.error('\n新的取值请加到 src/styles/theme.css 的 @theme 里，再从页面引用。')
  process.exit(1)
}
console.log('Style tokens: ok')
```

- [ ] **Step 2: 接进 npm scripts**

在 `frontend/package.json` 的 `scripts` 里加一行，放在 `check:boundaries` 旁边：

```json
"check:styles": "node scripts/check-style-tokens.mjs",
```

- [ ] **Step 3: 跑一次，确认通过**

```bash
npm run check:styles
```

期望输出：`Style tokens: ok`。如果还有报错，说明阶段四有文件没迁完——回去补完，**不要把它加进 ALLOWED_FILES 白名单**。

- [ ] **Step 4: 提交**

```bash
git add frontend/scripts/check-style-tokens.mjs frontend/package.json
git commit -m "chore(frontend): 加样式令牌检查，挡住裸字号与裸色值

styles/ 之外不许再出现写死的取值。这是这套设计系统唯一的强制机制。"
```

---

## 完成的判定标准

- `npm run check:styles` 通过，白名单里只有知识图谱那三个文件。
- `frontend/src` 下的 `.css` 文件只剩 `styles/theme.css`、`styles/tokens.css`、`styles/base.css`、`styles/app.css` 和知识图谱三个。
- 控件的定义只出现在 `shared/ui/control-classes.ts` 一处，全库 `button {` 规则数为 0。
- 每一页迁移前后的截图一致。
- `npx tsc -b`、`npx vitest run`（仅基线 5 个失败）、`npx oxlint`、`npm run check:boundaries` 全绿。

## 提示

阶段四的 `foundation.css` 有 4348 行，是全库最大的一个，建议放在最后并单独拆成多个提交（按页面区块拆）。如果做到一半发现某个模块的设计本身需要改，**记下来另开 issue**，不要在迁移提交里顺手改——迁移提交的唯一判定标准是观感不变，混进设计改动就没法验收了。
