# Zabbix 离线部署工具

基于 Bun + TypeScript + `@clack/prompts` 的交互式 TUI 工具，用于在离线环境中快速部署 Zabbix 7.0 LTS 全栈服务。

目标场景是：在有网络的机器上提前准备 Docker 镜像包，在目标离线机器上通过终端向导完成镜像加载、Compose 生成、服务启动、健康检查和基础初始化。

## 项目特性

- 交互式 TUI 向导，按步骤收集部署参数
- 支持离线镜像包检查与批量 `docker load`
- 自动生成 `docker-compose.yml` 并启动 Zabbix 服务栈
- 内置健康检查，轮询 PostgreSQL、Zabbix Server、Web、Agent 容器状态
- 部署完成后自动调用 Zabbix API，修正默认主机的 Agent 接口地址
- 支持查看状态、停止服务、彻底卸载等运维操作
- 支持可选的 SNMP Trapper 配置
- 提供 Docker 开发容器，便于在一致环境中安装依赖和运行测试

## 部署架构

默认部署的服务包括：

- PostgreSQL 16
- Zabbix Server 7.0 LTS
- Zabbix Web（Nginx + PHP）
- Zabbix Agent2
- 可选：Zabbix SNMP Traps

```text
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  PostgreSQL  │◄────│ Zabbix Server│────►│  Zabbix Web  │
│    (数据库)   │     │  (监控引擎)   │     │ (Nginx+PHP)  │
└──────────────┘     └──────┬───────┘     └──────────────┘
                            │
                     ┌──────┴───────┐
                     │ Zabbix Agent │
                     └──────────────┘
```

## 适用场景

- 无公网访问能力的机房或内网环境
- 希望通过统一向导快速完成 Zabbix 初始部署
- 需要将部署流程标准化、减少手工 Compose 编写
- 需要本地开发、测试一套离线部署工具链

## 技术栈

| 组件 | 选型 |
| --- | --- |
| 运行时 | Bun |
| 语言 | TypeScript（strict） |
| 交互 | `@clack/prompts` |
| 配置校验 | Zod |
| YAML 生成 | yaml |
| 代码规范 | Biome |
| 容器编排 | Docker / Docker Compose |

## 主要功能

### 1. 部署 Zabbix

部署流程大致如下：

1. 检查 Docker / Docker Compose 可用性
2. 检查 `packages/` 中的离线镜像包
3. 交互式收集部署参数
4. 生成部署目录下的 `docker-compose.yml`
5. 启动 Zabbix 服务栈
6. 等待容器健康检查通过
7. 调用 Zabbix API 做部署后初始化

默认会收集或生成的关键配置包括：

- 部署目录，默认 `/opt/zabbix`
- 数据库密码
- Zabbix Web 访问端口，默认 `8080`
- 时区，默认 `Asia/Shanghai`
- Server 监听端口，默认 `10051`
- 缓存大小、Poller 数量等高级参数
- 是否启用 SNMP Trapper 及其端口

### 2. 检查状态

可查看：

- Docker 镜像是否已加载
- Compose 容器运行状态与健康状态
- 默认部署目录与 Compose 文件是否存在

### 3. 停止服务

执行 `docker compose down --remove-orphans`，仅停止并移除容器与网络，保留：

- 数据卷
- Docker 镜像
- 部署目录与 Compose 文件

### 4. 彻底清理

支持一键清理以下资源：

- 容器与网络
- 数据卷
- Docker 镜像
- 部署目录

该操作不可逆。

## 快速开始

### 环境要求

宿主机本地构建或运行 TUI 时需要：

- Bun
- Docker
- Docker Compose

其中：

- `bun install`、`bun test` 等依赖安装与测试，推荐在开发容器内执行
- `bun run build` 可直接在宿主机执行，产出单文件二进制

### 1. 安装依赖

推荐方式：使用开发容器。

```bash
bun run docker:dev
```

另开终端进入容器：

```bash
bun run docker:shell
```

在容器内安装依赖：

```bash
bun install
```

如果你已经在本机具备完整环境，也可以直接执行：

```bash
bun install
```

### 2. 准备离线镜像包

在有网络的机器上执行：

```bash
bash scripts/save-images.sh
```

脚本会拉取并保存以下镜像到 `packages/`：

- `postgres:16-alpine`
- `zabbix/zabbix-server-pgsql:alpine-7.0-latest`
- `zabbix/zabbix-web-nginx-pgsql:alpine-7.0-latest`
- `zabbix/zabbix-agent2:alpine-7.0-latest`

然后将生成的 `.tar` 文件拷贝到目标离线机器的 `packages/` 目录。

如果你计划启用 SNMP Trapper，还需要额外准备以下镜像包：

```bash
docker pull zabbix/zabbix-snmptraps:alpine-7.0-latest
docker save -o packages/zabbix-zabbix-snmptraps-alpine-7.0-latest.tar zabbix/zabbix-snmptraps:alpine-7.0-latest
```

### 3. 启动交互式部署

```bash
bun run dev
```

启动后可在 TUI 中选择：

- `部署 Zabbix`
- `检查状态`
- `停止服务`
- `彻底清理`
- `退出`

### 4. 构建单文件可执行程序

```bash
bun run build
```

输出文件：

- `build/zabbix-deploy`

可直接在目标机器执行：

```bash
./build/zabbix-deploy
```

## 常用命令

### 本地开发

```bash
bun run dev
bun run build
bun run lint
bun run format
bun run check
bun run typecheck
bun test
bun run clean
```

### Docker 开发环境

```bash
bun run docker:dev
bun run docker:dev:down
bun run docker:shell
bun run docker:test
bun run docker:zabbix
bun run docker:zabbix:down
```

## 目录结构

```text
.
├── docker/               # 开发容器与测试环境 Compose
├── packages/             # 离线镜像 tar 包目录
├── scripts/              # 辅助脚本（如离线镜像下载）
├── src/
│   ├── cli/              # TUI 交互入口与流程编排
│   ├── config/           # 配置采集与 Compose 生成
│   ├── core/             # 部署、状态、健康检查、清理逻辑
│   ├── services/         # Docker、镜像、Zabbix API 等服务封装
│   ├── types/            # 常量、类型与 Schema
│   └── utils/            # 通用工具
├── tests/                # 单元测试
└── README.md
```

## 默认配置说明

| 项目 | 默认值 |
| --- | --- |
| 部署目录 | `/opt/zabbix` |
| Compose 项目名 | `zabbix` |
| Zabbix Web HTTP 端口 | `8080` |
| Zabbix Web HTTPS 端口 | `8443` |
| Zabbix Server 端口 | `10051` |
| Zabbix Agent 端口 | `10050` |
| 数据库 | PostgreSQL 16 |
| Zabbix 版本 | 7.0 LTS |
| 默认 Web 登录账号 | `Admin / zabbix` |

部署成功后通常可通过以下地址访问：

```text
http://localhost:8080
```

如果部署时修改了端口，请使用实际端口访问。

## 测试

推荐在开发容器内执行测试：

```bash
bun run docker:test
```

也可以直接运行：

```bash
bun test
bun test --watch
bun test --coverage
```

当前测试主要覆盖：

- 配置 Schema 校验
- Compose 文件生成
- Docker 相关类型与清理逻辑
- 命令执行工具函数

## 开发说明

- 代码基于 TypeScript strict 模式
- 导入路径需显式带 `.ts` 扩展名
- 使用 Biome 做格式化与 lint
- 以纯函数和模块单一职责为主
- 测试使用 Bun 内置测试框架

## 注意事项

- `packages/` 中的离线镜像包不应提交到仓库
- 彻底清理会删除数据库数据卷，请务必谨慎操作
- 首次部署时 Zabbix 初始化数据库可能耗时数分钟
- 工具会在部署后尝试自动修正默认主机 `Zabbix server` 的 Agent 接口地址
- 若目标环境的 Docker 策略、端口占用或镜像准备不完整，可能导致健康检查失败

## 后续可扩展方向

- 支持导入/导出部署配置文件
- 支持更多 Zabbix 组件与可选服务模板
- 支持更完整的离线包校验与版本校验
- 支持日志查看与故障诊断向导
