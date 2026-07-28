# 工程笔记

## 2026-07-28 架构依据

- Vite 8 要求 Node 20.19+ 或 22.12+：https://vite.dev/guide/
- React 应用只创建一个 root，错误边界由应用壳统一处理：https://react.dev/reference/react-dom/client/createRoot
- FastAPI 生成 OpenAPI，前端类型从该契约生成：https://fastapi.tiangolo.com/advanced/generate-clients/
- Hey API 生成器固定精确版本：https://heyapi.dev/docs/openapi/typescript/get-started
- TanStack Query 轮询在终态返回 `false` 停止：https://tanstack.com/query/v5/docs/framework/react/guides/polling
- Alembic migration environment 与应用源码共同维护：https://alembic.sqlalchemy.org/en/latest/tutorial.html
