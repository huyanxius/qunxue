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
