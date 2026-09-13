# T7 — apps/web 骨架（eslint + tsc + vitest）

- blocking：T1

## 目标

React 19 + Vite + TS 的空 SPA 骨架，三件套（lint / typecheck / test）本地绿，为 M1 的四模块留位。

## 交付物

- `apps/web/`：Vite + React 19 + TS（strict），`src/main.tsx` / `src/App.tsx` 最小页面
- `eslint.config.js`（flat config：typescript-eslint + react-hooks + react-refresh）
- `vitest` + jsdom + @testing-library/react，1 个占位测试（渲染 App 并断言文案）
- `tsconfig.json`（strict、`noUncheckedIndexedAccess`）+ `vite.config.ts`
- `package.json` scripts：`lint` / `typecheck` / `test` / `build`

## 验收

| 命令 | 期望 |
| --- | --- |
| `pnpm -C apps/web lint` | exit 0，0 error |
| `pnpm -C apps/web typecheck` | exit 0 |
| `pnpm -C apps/web test -- --run` | 1 passed |
| `pnpm -C apps/web build` | 产物生成（骨架自检） |

## 形态提议（待确认）

- M0 不引 TanStack Query / zustand / shadcn（D05 的模块留 M1），避免空依赖与范围蔓延。
- 不接 OpenAPI 类型生成（D17）——等 M1 有真实端点后再接。

## 不做

- 不做页面/路由/样式体系/api-client。
