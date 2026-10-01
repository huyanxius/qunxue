# 学术前沿前端

入口 `/knowledge?scope=frontier`。沿用群学应用壳、可折叠知识库分组和原知识库设计规则。主界面没有重复的“学科/课程/前沿”导航。

## 软件结构

默认首页为全量研究总览，消费 `/api/frontier/overview` 的实质综述、分节论点与统计。只有 ready 状态且覆盖集合与当前全部研究记录精确一致时，才展示全量总述；实践观察分开计算。大证据集显示前三个编号与完整依据列表展开入口，编号按正文首次引用顺序形成，不使用馆藏索引。

“研究总览 / 研究议题 / 全部文献”和分析视图都使用 `styles/selection-controls.css` 的共享语义 token，采用填充式选择控件，无下划线选中样式。总览正文有短章节导航，主图仅呈现具备意义的主要议题、按时间排序的发表年份和来源分布；不将未填字段或待归类记录作为研究特点。

次级的研究议题页以紧凑议题行组织具体研究进展、文献来源和真实微趋势；点选打开全高分析面板，提供概览、综合解读、文献视图。有解读时展示逐项带引用的研究进展、共同发现、差异、方法和研究启发，没有聊天占位框或生成中的假状态。

概览图仅使用真实期次/月度序列。同一比较组至少两个完整期次才呈现占比；其余仅为明确出版日期文献的收录分布。来源条形图来自实际相关文献。引用按钮直接打开相应论文。

论文详情以摘要、问题、材料方法、发现和阅读价值为主，空字段不生成空标题。来源信息折叠收纳；CSS 抓取定位、采集过程和重复警告不进入阅读正文。

`FrontierSourceFigure` 展示服务核验的媒体及完整图注、原文链接。不以历史个案图充当当前总体趋势。无图或加载失败不展示占位图；使用 HTTPS、lazy loading 和 no-referrer。

## 数据连接与恢复

`FrontierConnectedPage` 经 `frontierApi.ts` 调用生成 SDK，分页读取持久化资料、主题、来源。服务失败显示重试，不降级到种子数据。

`researchBrief` 为正文综合分析；旧 `editorialBrief` 仍可兼容。引用与来源均通过实际记录 ID 关联。`monthlySeries`、`issueSeries` 和核验过的媒体由服务合同提供。记录删除、版本失效由后端处理，不在前端臆造共识和趋势。

首页视图（`section=topics|papers`）、关键词、类型、来源、议题、正文记录、分页数量和分析视图（`view=analysis|sources`）保存在 URL。打开引用后返回恢复分析视图，键盘可切换 tabs，关闭议题回到概览。记录仍可全部分页浏览。

`FrontierPreviewProvider` 仅供显式快照注入使用。是否已部署持续采集服务、是否完成真实浏览器验收，分别核对，不由静态构建代替。

## 检查

```sh
TZ=Asia/Shanghai npm run test -- --maxWorkers=2 src/modules/frontier src/modules/knowledge-explorer src/app/FrontierRoute.test.tsx src/app/ui/PageShell.test.tsx
npm run typecheck
npm run check:boundaries
npm run lint
npm run build
```

当前相关回归另包含全量总览、证据展开和共享选择 token 的检查。完整仓库另有 ResearchMapCanvas 点阵背景断言基线失败，不能将聚焦回归描述为全仓绿色。
