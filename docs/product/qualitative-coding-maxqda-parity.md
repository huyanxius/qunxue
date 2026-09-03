# 群学致知质性编码工作台：MAXQDA 核心工作流复刻开发文档

版本：v0.1 · 2026-09-04  
状态：研究完成，待分阶段实现

## 1. 目标与边界

### 1.1 产品目标

把“编码结果”从分析区里的抽象卡片，变成社会学研究者可以持续阅读、判断、修订和导出的编码文档：

- 原文是主阅读面，文本、段落顺序、章节层级和定位信息保持不变；
- 编码是附着在原文上的解释层，用页边 coding stripes / brackets、片段高亮和上下文面板呈现；
- 一段可以有多个编码，编码可以重叠、相交或包含，不能因为视觉简化而丢失关系；
- Agent 结果永远先以候选状态出现，研究者确认后才进入正式编码；
- 每个编码都能回到原文位置，每个引文都能看到来源、定位、备忘和决策状态；
- 视图与导出都必须保留可审计的证据链：原文 → 片段 → 编码 → 备忘/主题 → 研究判断。

### 1.2 非目标

- 不复制 MAXQDA 的品牌、图标、专有资产或软件内部实现；
- 不把“自动生成代码”当作无需人工审查的事实；
- 第一阶段不做完整的统计分析、转录时间轴编辑、图片区域编码和多人实时协同；
- 不改变已有材料解析、引用和研究任务主链。

### 1.3 复刻标准

“1:1”在本项目中指研究工作流和可观察交互对齐，不指像素级复制专有软件：同样的对象层级、同样的证据回链、同样的重叠编码语义、同样的检索和导出结果；视觉语言沿用群学致知现有的中性、现代、低干扰设计系统。

## 2. 外部产品拆解（以官方资料为依据）

### 2.1 MAXQDA Document Browser

MAXQDA 在原文左侧显示 coding stripes 或 coding brackets。编码条标出编码范围，支持显示代码名、悬停查看完整代码路径和权重，也支持切换编码条所在侧、显示哪些代码和是否以代码颜色高亮正文。[Coding Stripes 官方手册](https://www.maxqda.com/help/coding/visualizing-coded-segments-in-the-document-browser)

关键交互：

1. 文档浏览器是主工作区，不是结果列表的附属预览；
2. 编码条和正文位置严格对齐；
3. 代码可以在左侧代码系统中激活/停用，正文和编码条随筛选变化；
4. 重叠编码保持多条独立编码条；高亮是可选的，重叠过多时避免颜色混合；
5. 单击/悬停编码条能识别对应代码，双击或上下文菜单可以编辑片段评论；
6. 从 Retrieved Segments 结果点击来源，会把片段加载回 Document Browser 并高亮原文。

### 2.2 MAXQDA Code System

代码系统是树形层级，可包含父代码、子代码和多级子代码；代码可设置颜色、定义、纳入/排除规则、例证和代码备忘。代码系统可导出为 Word 或图像。[Code System 官方手册](https://www.maxqda.com/help/codes-2/about-codes-and-the-code-system)

对群学致知的要求：

- 代码必须有稳定 ID，不以显示名作为引用键；
- 父子关系、生命周期（active/merged/split/retired）可追踪；
- 定义与规则属于代码本身，不能埋在 Agent 提示词里；
- 代码激活状态是视图状态，不改变数据；
- 合并、拆分和废弃要保留历史关系。

### 2.3 Retrieved Segments / Coding Query

MAXQDA 的 Retrieved Segments 是按激活文档和激活代码编译的结果窗口。结果项包含原文、来源位置、编码条、备忘和其他编码；点击来源会跳回文档上下文；结果可以按文档顺序、代码顺序或权重排序，并能进入表格视图。[Retrieved Segments 官方手册](https://www.maxqda.com/help/segment-retrieval/the-retrieved-segments-window)

对群学致知的要求：

- 提供“按代码看证据”和“按材料看编码”两种入口；
- 每条结果显示材料名、页/段/行定位、原文上下文、全部相关代码；
- 结果可筛选、排序、复制带来源引用；
- 点击结果必须回到原文同一段，而不是打开一张脱离上下文的卡片。

### 2.4 备忘、评论和导出

MAXQDA 区分附着于片段的 in-document memo、代码 memo、代码系统 memo、自由 memo 等；编码片段还可以有短评论。片段评论用于快速摘要，memo 用于较长的分析、方法和理论记录。[Memo 类型说明](https://www.maxqda.com/help/memos/opening-and-editing-memos) · [编码片段评论](https://www.maxqda.com/help/coding/comments-for-coded-segments)

导出不是简单导出代码清单：MAXQDA 可以把带段落编号、编码条、memo 符号的完整文档导出 PDF，也可以把检索到的编码片段、来源、memo、其他代码导出为 DOCX、XLSX 或 HTML；Smart Publisher 则按代码树生成带目录的研究报告。[文档导出](https://www.maxqda.com/help/report-and-export/export-documents) · [检索片段导出](https://www.maxqda.com/help/segment-retrieval/print-export-retrieved-segments) · [Smart Publisher](https://www.maxqda.com/en/support/help/maxqda-12/Documents/smartpublisher.htm)

### 2.5 AI Coding 与人工确认

MAXQDA 的 AI Coding 以代码定义、纳入/排除标准和代码 memo 为依据，对文档提出候选片段和理由；结果完成后仍需人工逐条审查和最终确认。[AI Coding 官方手册](https://www.maxqda.com/help/ai-assist/ai-coding/coding-documents)

对群学致知的要求：

- Agent 候选必须显示“候选”标签、理由、来源和运行批次；
- 接受、拒绝、修改均写入决策记录；
- 候选不应伪装成研究者已经确认的正式编码；
- 批量编码结果要能逐条回到原文，不只显示统计数字。

### 2.6 质量与协作

MAXQDA 提供 Intercoder Agreement，对两个独立编码者在相同文档上的编码进行比较，输出代码级和片段级一致/不一致结果，重点是定位分歧并修订代码定义，而不是只追求一个百分比。[Intercoder Agreement 官方手册](https://www.maxqda.com/help/coding/problem-intercoder-agreement-qualitative-research?view=full)

第二阶段以后再实现：编码者身份、版本快照、差异表、重叠率阈值和分歧处理队列。

## 3. 研究对象与数据模型

### 3.1 对象关系

```text
ResearchTask
 ├─ Material ── Parse ── Segment
 │                         └─ Locator (page/paragraph/line/char)
 ├─ Annotation (selected evidence excerpt)
 │    ├─ CodeAssignment ── Code
 │    ├─ SegmentComment
 │    └─ MemoLink ── Memo
 ├─ CodeSystem
 │    └─ Code (parent/children, definition, rules, color, lifecycle)
 ├─ RetrievedQuery (active materials + active codes + filters)
 └─ ExportJob / ResearchReport
```

### 3.2 现有模型复用

当前仓库已有：

- `ResearchMaterial` / `ResearchMaterialSegment`：材料、解析版本、片段和定位；
- `AnalysisAnnotation`：片段标记、quote、locator、case、反思；
- `AnalysisCode`：代码、definition、rationale、annotation_ids、status、version；
- `AnalysisMemo`、`CodebookEntry`、`AnalysisTheme`、比较和矩阵对象；
- Alembic migration `20260903_0191`：批量编码运行记录。

第一阶段不重做后端对象；先在前端将 annotation → code 的关系真实映射到文档。第二阶段补充独立 `CodeAssignment` 与片段评论字段，避免把多个编码压扁到 `annotation_ids` 反向查询。

### 3.3 建议新增字段

```ts
type CodeAssignment = {
  assignmentId: string
  annotationId: string
  codeId: string
  status: 'candidate' | 'confirmed' | 'rejected'
  source: 'researcher' | 'agent'
  confidence: number | null
  rationale: string | null
  weight: number | null
  createdAt: string
  decidedAt: string | null
  version: number
}

type SegmentComment = {
  commentId: string
  annotationId: string
  content: string
  authorId: string
  createdAt: string
  updatedAt: string
}
```

## 4. 目标信息架构

### 4.1 三栏工作区

```text
┌──────────────┬──────────────────────────────┬────────────────────┐
│ 文档/章节     │ 文档浏览器                     │ 证据检查器           │
│              │ [行号][coding stripes][原文] │ 选中片段             │
│ 材料列表      │                              │ 代码                 │
│ 代码系统      │                              │ 定义/理由/评论/memo   │
│              │                              │ 来源定位/决策         │
└──────────────┴──────────────────────────────┴────────────────────┘
```

- 左栏：材料、章节目录、代码树、激活/停用代码；
- 中栏：保留原文阅读体验，左/右页边显示编码条；
- 右栏：选中片段的代码、代码定义、候选理由、评论、memo、来源和操作；
- 顶部工具栏：原文/编码视图、显示代码名、显示高亮、筛选、检索、导出、缩放；
- 底部状态栏：当前材料、当前页、编码数量、候选数量、未处理冲突。

### 4.2 文档浏览器视觉规则

1. 正文使用现有阅读字体和段落节奏，不把每段变成卡片；
2. 编码条使用窄色条/括号，垂直范围与片段首尾精确对齐；
3. 每个编码使用稳定的低饱和颜色，颜色只表达类别，不表达正确性；
4. 高亮默认只显示当前激活代码，避免重叠代码混色；
5. 代码名默认在悬停或选中时出现，常驻名称可由用户打开；
6. 有 memo 的片段显示独立 memo 标记，不把 memo 内容硬塞进正文；
7. 候选编码使用虚线/低对比度边框，与已确认编码区分；
8. 原文缺失或定位失效时显示明确的证据状态，不用占位文字冒充原文。

### 4.3 核心交互状态

| 状态 | 视觉 | 可用操作 |
| --- | --- | --- |
| 原文视图 | 无编码条，只显示正文 | 阅读、搜索、拖选标记 |
| 编码视图 | 显示激活编码条和可选高亮 | 点条查看代码、拖选新增编码 |
| 片段选中 | 当前片段边框/底色 | 查看、编辑、增加/移除代码、写评论 |
| 候选片段 | 虚线边框、候选徽标 | 接受、拒绝、修改、查看 Agent 理由 |
| 多编码重叠 | 多条平行编码条 | 分别选择、分别编辑、查看共现 |
| 失效定位 | 警告标记 | 查看原因、重新定位、保留审计记录 |

## 5. 功能分期

### Phase 0：研究与基础契约

- 固化本开发文档；
- 为 segment、annotation、code、memo 定义前端 view model；
- 确认分页、搜索、历史 parse 的定位规则；
- 不发布视觉草图。

完成标准：任意片段都能从分析记录定位回材料原文；不存在只显示代码名但找不到证据的状态。

### Phase 1：MAXQDA 核心文档浏览器

- `MaterialReaderView` 支持 coding stripes / brackets；
- 代码条按 segment 精确对齐；
- 支持多编码、重叠编码和候选/确认状态；
- 点击编码条打开右侧证据检查器；
- 支持原文视图、编码视图、仅当前激活代码；
- 保留拖选原文创建 annotation 的动作；
- 显示段落/页/行定位。

完成标准：研究者可以只在文档浏览器中完成“读 → 选片段 → 加代码 → 看定义/理由 → 回到原文”的闭环。

### Phase 2：代码系统与片段处理

- 左栏树形代码系统；
- 新建、重命名、移动、父子层级、颜色、定义、纳入/排除规则；
- 代码激活/停用；
- 片段评论和 memo；
- 代码合并、拆分、废弃保留历史。

完成标准：代码系统可以独立维护，视图筛选不改变底层数据。

### Phase 3：Retrieved Segments / Coding Query

- 按材料、代码、状态、案例、时间和来源筛选；
- 文档顺序、代码顺序、权重排序；
- 列表视图、表格视图、来源上下文跳转；
- 对检索结果批量追加代码；
- 显示所有重叠代码和 memo。

完成标准：一个代码可以一键编译出全部证据，并逐条跳回原文。

### Phase 4：导出与研究报告

- 编码文档 HTML：原文 + 段落号 + 页边编码条 + memo 图标；
- PDF：保留文档阅读版式，可选显示编码条和高亮；
- DOCX：表格版段落/行号、代码列、memo/comment 列；
- XLSX：一行一个编码片段，包含来源、代码、状态、理由和全部重叠代码；
- Smart Publisher：按代码树生成章节、目录和带来源引文的报告。

完成标准：导出结果能脱离应用阅读，仍能追溯到材料和片段定位。

### Phase 5：质量、协作与 Agent 辅助

- Intercoder Agreement：代码级/片段级差异表和重叠率阈值；
- 代码定义版本与审计日志；
- Agent 单代码批量建议、逐条解释、批量接受/拒绝；
- 运行中断、重试、幂等和结果版本；
- 团队导入/导出编码、memo 和变量。

完成标准：Agent 只能提出可审查候选，不能绕过研究者决策进入正式分析。

## 6. 前端实现方案

### 6.1 组件拆分

```text
ResearchMaterialsPanel
 ├─ MaterialLibraryView
 └─ CodedDocumentWorkbench
     ├─ DocumentOutline
     ├─ CodedDocumentReader
     │   ├─ SegmentBlock
     │   ├─ CodingStripeRail
     │   ├─ CodeHighlightLayer
     │   └─ LocatorAnchor
     ├─ CodeSystemSidebar
     ├─ EvidenceInspector
     ├─ RetrievedSegmentsView
     └─ ExportMenu
```

现有 `MaterialReaderView` 负责材料阅读和定位；第一阶段允许在其上增量演进，但不把编码筛选、代码树和导出逻辑继续堆进单文件。达到 Phase 2 时拆出 `CodedDocumentReader`。

### 6.2 文本定位算法

优先级：

1. `annotation.segment_id === segment.segmentId`；
2. 同一 `parse_id` 且 locator 的 paragraph/line/block 相交；
3. quote 在 segment.text 中精确匹配；
4. 无法精确匹配时显示整段候选范围，并标记 `定位需复核`；
5. 永不静默把另一个段落当作目标。

编码条必须使用定位范围渲染，而不是只根据“这个 segment 有 annotation”给整段染色。第一阶段可以按 segment 级条带交付，Phase 2 必须支持 quote 的字符级首尾。

### 6.3 性能

- 文档分页沿用现有 24 段一页；
- 编码索引在渲染前按 `segment_id` 建 `Map`，禁止每个段落重复扫描全量 annotations/codes；
- 代码筛选只改变可见映射，不重新请求材料正文；
- 大文档使用虚拟列表前，先保证定位跳转和选区拖选正确；
- 导出使用后端任务，前端显示进度和可重试状态。

## 7. 后端与 API 规划

现有分析 API 继续作为第一阶段数据源：

- `GET /api/research/tasks/{task_id}/analysis`：快照；
- `POST .../annotations`：手动片段标记；
- `POST .../codes`：创建代码并绑定片段；
- `POST .../codes/{code_id}/decision`：候选代码决策；
- `POST .../batch-coding`：批量编码运行。

第二阶段新增：

- `GET /analysis/codes/tree`：树形代码系统；
- `PATCH /analysis/codes/{id}`：代码定义、颜色、层级和生命周期；
- `POST /analysis/annotations/{id}/assignments`：独立代码绑定；
- `POST /analysis/annotations/{id}/comments`：片段评论；
- `GET /analysis/retrieved-segments`：筛选、排序、分页和上下文来源；
- `POST /analysis/exports` / `GET /analysis/exports/{id}`：异步导出。

所有写操作要求幂等键、期望版本和审计记录；候选与正式状态不得通过前端字段伪造转换。

## 8. 验收标准

### 8.1 文档浏览器

- 打开有编码的材料，正文与无编码版本逐字一致；
- 每个已确认编码都有独立编码条；
- 同一片段三个编码显示三条可区分的条；
- 点编码条，右侧显示代码名、定义、状态、来源和片段原文；
- 点来源定位，文档滚动到同一段；
- 切换代码筛选后，只隐藏/显示对应条，不改变正文顺序；
- 候选编码与确认编码视觉可区分；
- 搜索、分页、章节跳转不会丢失编码定位。

### 8.2 研究语义

- quote、locator、segment_id、parse_id 全部保留；
- 解析版本变化后，旧引用显示历史版本或定位失效原因；
- 拒绝的候选不出现在正式编码视图，但审计记录仍可查看；
- Agent 理由和研究者决定分开呈现；
- 导出包含材料名、段落/页/行定位和全部相关代码。

### 8.3 视觉验收

- 不使用整片高饱和色块，不使用渐变和彩色玻璃卡片；
- 正文仍像一份可连续阅读的社会学材料，而不是数据库表格；
- 编码条足够窄，不挤压正文；
- 右侧检查器打开/关闭不破坏正文宽度和定位；
- 多编码重叠不出现难以辨认的混色；
- 键盘焦点、悬停、选中和候选状态均有明确但克制的反馈。

## 9. 当前实现决策

当前线上已回滚到稳定阅读器。此前的 `bb9e70b` 只包含一个未完成的编码视图草图，不能作为本功能的交付版本。后续实现必须先完成 Phase 0 文档和 Phase 1 闭环，再部署；不把单次构建成功或一张状态卡片当作“MAXQDA 复刻完成”。

