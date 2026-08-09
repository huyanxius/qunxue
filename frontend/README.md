# 群学致知 Web

前端按产品任务组织：

```text
app → module index.ts → generated OpenAPI transport
```

`socio-match-workspace` 负责研究任务创建、恢复和工作区；`knowledge-explorer` 负责知识浏览。产品模块只能从 `index.ts` 对外开放，页面不得裸调用 `fetch` 或手写后端 DTO。

```bash
npm ci --ignore-scripts
npm run generate:api
npm run dev
```

开发时 Vite 将 `/api` 代理到 `http://127.0.0.1:8000`。

## 知识库浏览

访问 `http://127.0.0.1:5173/knowledge` 可直接打开知识库浏览页面，也可以从首页进入。首次进入会读取当前可浏览发布，并把 `knowledge_release_id` 写入 URL；目录、搜索和详情随后固定在同一发布版本内。列表显示条目所属维度和完整目录位置，详情显示正文、来源、审核状态与已审核显式关系。

`knowledge-explorer/knowledgeApi.ts` 只通过生成的 OpenAPI SDK 读取真实发布数据，并将 DTO 映射为模块界面模型；页面不调用 `fetch`，也不保留浏览器端 Mock 数据源。正文使用 `react-markdown` 渲染 Markdown，未启用原始 HTML；关系只显示 API 返回且审核状态为 `reviewed` 的记录。带 `return_to` 的详情页仅接受 `/research/` 内的返回路径。

当前发布中的待审核条目或待核验来源会如实标记，不应被理解为已核实的学术结论。图形视图不属于该模块的知识浏览基线。

部署构建产物时，静态服务器需要把 `/knowledge` 等前端路由回退到 `index.html`，否则浏览器直接访问或刷新子路径会返回服务器 404。可以用以下命令验证构建后的直达访问：

```bash
npm run build
npm run preview
```
