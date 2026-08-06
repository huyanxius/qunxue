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

访问 `http://127.0.0.1:5173/knowledge` 可直接打开知识库浏览页面，也可以从首页进入。当前页面使用模块内的虚构演示数据，只用于验证列表、详情、来源、审核状态、关系、搜索和页面状态，不代表正式知识库或真实审核结论，也不会调用 RAG 或模型服务。

演示数据通过 `KnowledgeExplorerDataSource` 接口注入。接入正式知识接口时，应在模块 adapter 中把生成的 OpenAPI DTO 映射为该接口使用的稳定模型，不得在页面中裸调用 `fetch`。

部署构建产物时，静态服务器需要把 `/knowledge` 等前端路由回退到 `index.html`，否则浏览器直接访问或刷新子路径会返回服务器 404。可以用以下命令验证构建后的直达访问：

```bash
npm run build
npm run preview
```
