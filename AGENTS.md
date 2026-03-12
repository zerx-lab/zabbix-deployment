# AGENTS.md — Zabbix 离线部署工具

## 项目概述

Zabbix 离线部署工具，基于 Bun + TypeScript + @clack/prompts 构建交互式 TUI 部署方案。
目标：在无网络环境下通过交互式终端向导完成 Zabbix 7.0 LTS 全栈部署。
**依赖安装与测试默认在 Docker 容器中执行；TUI 二进制可直接在宿主机本地构建。**

## 技术栈

| 组件          | 选型                          |
|--------------|-------------------------------|
| 运行时        | Bun (latest)                  |
| 语言          | TypeScript (strict mode)      |
| TUI 交互      | @clack/prompts                |
| 配置校验      | Zod                           |
| Lint/Format  | Biome                         |
| 容器化        | Docker + Docker Compose       |
| 数据库        | PostgreSQL 16                 |
| 监控平台      | Zabbix 7.0 LTS (Alpine 镜像) |

## 项目结构

```
├── AGENTS.md                    # 本文件 — Agent 编码指南
├── package.json                 # Bun 项目配置与脚本
├── tsconfig.json                # TypeScript 编译配置
├── biome.json                   # Biome lint/format 规则
├── bunfig.toml                  # Bun 运行时配置
├── docker/
│   ├── Dockerfile.dev           # 开发环境容器 (bun + docker-cli)
│   ├── docker-compose.dev.yml   # 开发环境编排
│   └── docker-compose.zabbix.yml # Zabbix 全栈测试环境
├── src/
│   ├── index.ts                 # 应用入口
│   ├── cli/                     # TUI 交互层（用户输入/输出）
│   ├── core/                    # 核心部署逻辑（编排、检查）
│   ├── services/                # 各服务操作（Docker、镜像加载等）
│   ├── config/                  # 配置管理与模板渲染
│   ├── utils/                   # 通用工具（exec、logger 等）
│   └── types/                   # TypeScript 类型定义 + Zod Schema
├── templates/                   # Zabbix 配置文件模板
├── packages/                    # 离线安装包存放 (Docker 镜像 tar)
├── scripts/                     # 辅助脚本
└── tests/                       # 测试文件（镜像 src/ 结构）
```

## 构建 / Lint / 测试命令

### 依赖安装（在 Docker 容器内执行）

```bash
bun install
```

### 开发运行

```bash
bun run dev                   # 启动 TUI 工具
```

### 构建（编译为单文件可执行二进制）

```bash
bun run build                 # 输出到 build/zabbix-deploy
```

### Lint & 格式化

```bash
bun run lint                  # 仅检查
bun run format                # 自动格式化
bun run check                 # lint + format 一起修复
bun run typecheck             # TypeScript 类型检查
```

### 测试

```bash
bun test                      # 运行全部测试
bun test tests/utils/exec.test.ts   # 运行单个测试文件
bun test --watch              # watch 模式
bun test --coverage           # 带覆盖率
bun test -t "should execute"  # 按名称过滤运行测试
```

### Docker 开发环境

```bash
bun run docker:dev            # 构建并进入开发容器
bun run docker:shell          # 进入运行中的开发容器 shell
bun run docker:test           # 在容器中运行测试
bun run docker:zabbix         # 启动 Zabbix 全栈测试环境
bun run docker:zabbix:down    # 停止并清理 Zabbix 环境
```

## 代码风格规范

### 格式化（由 Biome 强制执行）

- 缩进：2 空格（禁止 Tab）
- 行宽：100 字符
- 换行符：LF
- 引号：单引号
- 分号：始终使用
- 尾逗号：始终添加（trailing commas: all）
- 箭头函数参数：始终加括号

### 导入规范

- 使用 `import type` 导入纯类型（TypeScript `verbatimModuleSyntax` 已开启）
- 导入路径必须带 `.ts` 扩展名（Bun 要求）
- 导入顺序由 Biome `organizeImports` 自动管理：外部依赖在前，内部模块在后
- 使用 `@/*` 路径别名引用 `src/` 下的模块

```typescript
import type { DeployConfig } from '../types/config.ts';  // 类型导入
import { z } from 'zod';                                  // 外部依赖
import { logger } from '../utils/logger.ts';              // 内部模块
```

### 命名规范

| 对象             | 风格          | 示例                        |
|-----------------|---------------|----------------------------|
| 文件/目录        | kebab-case    | `deploy-config.ts`         |
| 函数             | camelCase     | `checkDocker()`            |
| 变量/参数        | camelCase     | `cacheSize`                |
| 常量             | UPPER_SNAKE   | `MAX_RETRY_COUNT`          |
| 类型/接口        | PascalCase    | `DeployConfig`             |
| Zod Schema      | PascalCase+Schema | `DeployConfigSchema`   |
| 枚举值           | PascalCase    | `ServiceStatus.Running`    |

### 类型规范

- 开启 `strict` 模式，禁止隐式 `any`
- 优先使用 `interface` 定义对象类型，`type` 用于联合/交叉/工具类型
- 所有公开函数必须有显式返回类型标注
- 使用 Zod schema 做运行时校验，用 `z.infer<>` 派生 TypeScript 类型
- 禁止使用 `as` 类型断言，除非有注释说明原因
- 使用 `unknown` 而非 `any` 处理未知数据

### 错误处理

- 可预见错误使用 `Result` 模式或返回 `{ success, error }` 对象
- 不可恢复错误使用 `throw new Error()` 并在最外层统一捕获
- `catch` 中的错误类型标注为 `unknown`，在使用前做类型检查
- 外部命令执行（exec）始终检查 `exitCode`，不假设成功
- 用户输入始终通过 Zod schema 校验

```typescript
// 错误处理示例
try {
  await deploy(config);
} catch (error: unknown) {
  if (error instanceof Error) {
    logger.error(error.message);
  }
  process.exit(1);
}
```

### 函数与模块设计

- 优先使用纯函数，避免不必要的 class
- 每个模块（文件）专注单一职责
- 使用 barrel exports（`index.ts`）管理模块公开 API
- 异步函数始终使用 `async/await`，禁止裸 `.then()` 链
- 未使用的参数前缀 `_`（如 `_config`）

### 注释规范

- 公开函数和类型使用 JSDoc `/** */` 注释
- 行内注释使用 `//`，与代码保持 1 个空格
- 中文注释优先（本项目面向中文用户）
- TODO 格式：`// TODO: 描述`

## Docker 开发原则

1. `bun install`、`bun test` 等依赖安装与测试操作默认在容器内执行，`bun run build` 可直接在宿主机本地运行
2. 开发容器挂载项目目录，代码修改实时同步
3. 开发容器通过 Docker Socket 与宿主 Docker 通信（Docker-in-Docker 模式）
4. Zabbix 测试栈使用独立 compose 文件，与开发环境解耦
5. 离线镜像 tar 文件放在 `packages/` 目录，不提交到 Git

## 测试规范

- 测试文件命名：`<module>.test.ts`，放在 `tests/` 目录下镜像 `src/` 结构
- 使用 Bun 内置测试框架：`describe`、`it`、`expect`
- 每个公开函数至少一个正向和一个反向测试用例
- 测试中允许使用 `console`（Biome 规则已豁免）
- Mock 外部依赖（Docker 命令等），不在单元测试中调用真实系统

## Zabbix 部署架构

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  PostgreSQL  │◄────│ Zabbix Server│────►│  Zabbix Web  │
│    (数据库)   │     │  (监控引擎)   │     │ (Nginx+PHP)  │
└──────────────┘     └──────┬───────┘     └──────────────┘
                            │
                     ┌──────┴───────┐
                     │ Zabbix Agent │ (部署在被监控节点)
                     └──────────────┘
```

- 版本：Zabbix 7.0 LTS（Alpine 镜像）
- 数据库：PostgreSQL 16
- 前端：Nginx + PHP（zabbix-web-nginx-pgsql 镜像）
- 所有组件通过 Docker Compose 编排
