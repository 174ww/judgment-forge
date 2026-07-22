# Web shell (研判工坊)

Next.js App Router 工作台：注册/登录 → 项目 → 材料 → 启 run → HITL → 备忘录/清单/Trace。

## Setup

```bash
npm install
```

可选：复制环境变量（默认 API `http://localhost:8000`）：

```bash
copy .env.example .env.local
```

## Dev

先启动 API（见仓库根 README），再：

```bash
npm run dev
```

打开 [http://localhost:3000](http://localhost:3000)。

## Tests

薄 API 客户端缝（非 React）：

```bash
npm test
```
