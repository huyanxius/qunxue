# 前端门禁既有命中

[基线表](../scripts/frontend-check-baseline.json)记录 R03 开工时 `9869b21` 的命中。修复一项时同步删去对应条目。

| 检查 | 既有命中 | 计数方式 |
| --- | ---: | --- |
| FE-04 私有 CSS 引用 | 5 | TS/TSX 引用文件和 CSS 路径，包括 `CourseKnowledgePage` 引入的两份样式 |
| FE-05 适配器导出签名 | 73 | 每个导出函数的命中参数及返回值各计一次。`api/researchWorkspace.ts` 占 33 处 |
| FE-05 教学类型别名 | 13 | `teachingApi.ts` 原有的生成类型别名逐名登记，教学模块仍通过公共入口使用该适配器 |
| FE-08 缺少静态定义和 fallback 的 CSS 引用 | 48 | 按文件、选择器、属性、变量名和出现次数登记 |
| 工作台旧圆角检查 | 1 | `research-document-workbench.css` 中 `.research-map__document-focus > .research-document-map-node` 的 `border-radius: 0` |

FE-04 的共享样式迁移包括 `research-materials.css` 中的 `.qx-button`、`.qx-icon-button`、`.qx-field` 和 `.qx-message`。`MethodPlanWorkspace.tsx` 使用 `.qx-button`，依赖材料模块已加载的全局样式。 [样式定义](../src/modules/research-materials/research-materials.css) [使用位置](../src/modules/research-method/MethodPlanWorkspace.tsx)

FE-05 的账户适配器有 5 个手写的命名响应类型 `RawPreferences`、`RawAccount`、`RawSession`、`RawCreditSummary`、`RawAdminUser`，还有 10 处 `requestJson<{ … }>` 响应类型。它们是手工盘点项，签名规则追踪的是生成契约的类型来源。工作台的 6 个 `Awaited<ReturnType<…>>` 别名依赖 `researchWorkspace` 的返回结构。 [账户适配器](../src/modules/account/accountManagementApi.ts) [文档工作台](../src/app/research-workspace/ResearchDocumentWorkbench.tsx)

FE-08 从 `src` 内的 CSS 和已加载的 Tailwind 主题收集属性声明。合法主题覆盖共享同一个声明名。48 处静态命中中，`--qx-color-surface-subtle` 20 处，`--qx-space-5` 4 处，`--app-accent` 2 处，`--radius-card` 1 处。其余 21 处由 `KineticCopyCycle`、`FoundationAgentReveal`、`ResearchMaterialsPage`、`CodedDocumentWorkbench` 和 `KnowledgeCatalog` 的运行时内联样式提供。
