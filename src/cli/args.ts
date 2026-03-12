import type { Action } from './main.ts';

/** CLI 模式下 deploy 命令的参数 */
export interface DeployArgs {
  deployDir: string;
  dbPassword: string;
  webPort: number;
  timezone: string;
  serverPort: number;
  cacheSize: string;
  startPollers: number;
  enableSnmpTrapper: boolean;
  snmpTrapperPort: number;
}

/** 解析后的命令行参数 */
export interface ParsedArgs {
  /** 子命令（null 表示进入交互式 TUI） */
  command: Action | null;
  /** 是否自动确认所有操作 */
  autoConfirm: boolean;
  /** 是否显示帮助信息 */
  help: boolean;
  /** deploy 命令的参数 */
  deployArgs: Partial<DeployArgs>;
}

const VALID_COMMANDS = new Set<Action>(['install-docker', 'deploy', 'status', 'stop', 'uninstall']);

const HELP_TEXT = `
Zabbix 离线部署工具

用法: zabbix-deploy [命令] [选项]

命令:
  install-docker       安装 Docker（从离线包）
  deploy               部署 Zabbix
  status               检查服务状态
  stop                 停止服务
  uninstall            彻底清理

通用选项:
  -y, --yes            自动确认所有操作（跳过确认提示）
  -h, --help           显示帮助信息

Deploy 选项:
  --deploy-dir <path>       部署目录（默认 /opt/zabbix）
  --db-password <password>  数据库密码（必填，至少 8 位）
  --web-port <port>         Web 访问端口（默认 8080）
  --timezone <tz>           时区（默认 Asia/Shanghai）
  --server-port <port>      Server 监听端口（默认 10051）
  --cache-size <size>       缓存大小（默认 128M）
  --start-pollers <n>       Poller 数量（默认 5）
  --enable-snmp-trapper     启用 SNMP Trap 接收
  --snmp-trapper-port <port> SNMP Trap 端口（默认 162）

示例:
  # 交互式 TUI 模式
  ./zabbix-deploy

  # 直接安装 Docker（自动确认）
  ./zabbix-deploy install-docker -y

  # 查看状态
  ./zabbix-deploy status

  # 部署 Zabbix（CLI 模式）
  ./zabbix-deploy deploy -y --db-password mypassword123

  # 停止服务（自动确认）
  ./zabbix-deploy stop -y

  # 彻底清理（自动确认）
  ./zabbix-deploy uninstall -y
`.trim();

/** 显示帮助信息 */
export function showHelp(): void {
  console.log(HELP_TEXT);
}

/** 解析命令行参数 */
export function parseArgs(argv: string[]): ParsedArgs {
  // 跳过 bun/node 和脚本路径
  const args = argv.slice(2);

  const result: ParsedArgs = {
    command: null,
    autoConfirm: false,
    help: false,
    deployArgs: {},
  };

  let i = 0;
  while (i < args.length) {
    const arg = args[i] as string;

    // 子命令
    if (!arg.startsWith('-') && !result.command) {
      if (VALID_COMMANDS.has(arg as Action)) {
        result.command = arg as Action;
        i++;
        continue;
      }
      console.error(`未知命令: ${arg}`);
      console.error('使用 --help 查看可用命令');
      process.exit(1);
    }

    switch (arg) {
      case '-y':
      case '--yes':
        result.autoConfirm = true;
        break;

      case '-h':
      case '--help':
        result.help = true;
        break;

      case '--deploy-dir':
        result.deployArgs.deployDir = requireValue(args, i, arg);
        i++;
        break;

      case '--db-password':
        result.deployArgs.dbPassword = requireValue(args, i, arg);
        i++;
        break;

      case '--web-port':
        result.deployArgs.webPort = requirePort(args, i, arg);
        i++;
        break;

      case '--timezone':
        result.deployArgs.timezone = requireValue(args, i, arg);
        i++;
        break;

      case '--server-port':
        result.deployArgs.serverPort = requirePort(args, i, arg);
        i++;
        break;

      case '--cache-size':
        result.deployArgs.cacheSize = requireValue(args, i, arg);
        i++;
        break;

      case '--start-pollers': {
        const val = requireValue(args, i, arg);
        const n = Number(val);
        if (Number.isNaN(n) || n < 1 || n > 100) {
          console.error(`${arg} 值无效: ${val}（应为 1-100 之间的数字）`);
          process.exit(1);
        }
        result.deployArgs.startPollers = n;
        i++;
        break;
      }

      case '--enable-snmp-trapper':
        result.deployArgs.enableSnmpTrapper = true;
        break;

      case '--snmp-trapper-port':
        result.deployArgs.snmpTrapperPort = requirePort(args, i, arg);
        i++;
        break;

      default:
        console.error(`未知选项: ${arg}`);
        console.error('使用 --help 查看可用选项');
        process.exit(1);
    }

    i++;
  }

  return result;
}

/** 读取下一个参数值，不存在则报错退出 */
function requireValue(args: string[], index: number, flag: string): string {
  const next = args[index + 1];
  if (next === undefined || next.startsWith('-')) {
    console.error(`${flag} 需要一个值`);
    process.exit(1);
  }
  return next;
}

/** 读取端口号参数 */
function requirePort(args: string[], index: number, flag: string): number {
  const val = requireValue(args, index, flag);
  const port = Number(val);
  if (Number.isNaN(port) || port < 1 || port > 65535) {
    console.error(`${flag} 端口号无效: ${val}（应为 1-65535）`);
    process.exit(1);
  }
  return port;
}

/** 检查当前是否在交互式终端中运行 */
export function isTTY(): boolean {
  return process.stdin.isTTY === true;
}
