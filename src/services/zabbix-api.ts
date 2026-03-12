import { existsSync, readFileSync } from 'node:fs';
import { CONTAINER_NAMES } from '../types/constants.ts';

/** Zabbix API JSON-RPC 请求体 */
interface ZabbixRpcRequest {
  jsonrpc: '2.0';
  method: string;
  params: Record<string, unknown>;
  id: number;
  auth?: string;
}

/** Zabbix API JSON-RPC 响应体 */
interface ZabbixRpcResponse {
  jsonrpc: '2.0';
  result?: unknown;
  error?: { code: number; message: string; data: string };
  id: number;
}

/** 主机接口信息 */
interface HostInterface {
  interfaceid: string;
  hostid: string;
  ip: string;
  dns: string;
  useip: string;
  port: string;
  type: string;
}

/** 主机信息 */
interface ZabbixHost {
  hostid: string;
  host: string;
  interfaces: HostInterface[];
}

/** 初始化结果 */
export interface PostInitResult {
  success: boolean;
  agentInterfaceFixed: boolean;
  error?: string;
}

const DEFAULT_CREDENTIALS = {
  username: 'Admin',
  password: 'zabbix',
} as const;

/**
 * Zabbix API 等待超时时间（毫秒）
 *
 * 首次部署时 Zabbix Server 需要初始化数据库 schema，
 * 这个过程可能需要 3-5 分钟，因此设置较长的超时。
 */
const API_WAIT_TIMEOUT_MS = 300_000;

/** API 轮询间隔（毫秒） */
const API_POLL_INTERVAL_MS = 5_000;

/**
 * 检测当前进程是否运行在 Docker 容器内
 *
 * 通过检查 /.dockerenv 文件判断（Docker 创建容器时自动生成）。
 */
function isRunningInContainer(): boolean {
  return existsSync('/.dockerenv');
}

/**
 * 从容器内读取宿主机 IP
 *
 * 在 Linux 容器中，/proc/net/route 的默认路由（Destination=00000000）
 * 的 Gateway 字段是小端序十六进制，解析后即为宿主机网关 IP。
 * 通过该 IP 访问宿主机的端口映射（等同于从外部访问 localhost:{port}）。
 */
function getHostGatewayIp(): string | null {
  try {
    const content = readFileSync('/proc/net/route', 'utf-8');
    for (const line of content.split('\n').slice(1)) {
      const fields = line.trim().split(/\s+/);
      // Destination == 00000000 表示默认路由
      if (fields[1] === '00000000' && fields[2] && fields[2] !== '00000000') {
        // Gateway 字段是小端序十六进制，需逐字节反转后转为点分十进制
        const hex = fields[2];
        const ip = [
          Number.parseInt(hex.slice(6, 8), 16),
          Number.parseInt(hex.slice(4, 6), 16),
          Number.parseInt(hex.slice(2, 4), 16),
          Number.parseInt(hex.slice(0, 2), 16),
        ].join('.');
        return ip;
      }
    }
  } catch {
    // 无法读取路由表，返回 null
  }
  return null;
}

/**
 * 构建 Zabbix API 地址
 *
 * - 宿主机运行：直接用 localhost:{webPort}
 * - 容器内运行：通过宿主机网关 IP 访问端口映射（{gatewayIp}:{webPort}）
 */
function buildApiUrl(webPort: number): string {
  if (!isRunningInContainer()) {
    return `http://localhost:${webPort}/api_jsonrpc.php`;
  }

  const gatewayIp = getHostGatewayIp();
  if (gatewayIp) {
    return `http://${gatewayIp}:${webPort}/api_jsonrpc.php`;
  }

  // 回退：使用常见的 Docker bridge 默认网关（不可靠，但总比不尝试好）
  return `http://172.17.0.1:${webPort}/api_jsonrpc.php`;
}

/**
 * 调用 Zabbix JSON-RPC API
 */
async function rpcCall(
  apiUrl: string,
  method: string,
  params: Record<string, unknown>,
  authToken?: string,
): Promise<ZabbixRpcResponse> {
  const body: ZabbixRpcRequest = {
    jsonrpc: '2.0',
    method,
    params,
    id: 1,
  };
  if (authToken) {
    body.auth = authToken;
  }

  const response = await fetch(apiUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json-rpc' },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new Error(`Zabbix API HTTP 错误: ${response.status} ${response.statusText}`);
  }

  return (await response.json()) as ZabbixRpcResponse;
}

/**
 * 登录 Zabbix API 获取认证令牌
 */
async function login(apiUrl: string): Promise<string> {
  const resp = await rpcCall(apiUrl, 'user.login', {
    username: DEFAULT_CREDENTIALS.username,
    password: DEFAULT_CREDENTIALS.password,
  });

  if (resp.error) {
    throw new Error(`Zabbix 登录失败: ${resp.error.data}`);
  }

  return resp.result as string;
}

/**
 * 获取默认 "Zabbix server" 主机信息及接口
 */
async function getDefaultHost(apiUrl: string, authToken: string): Promise<ZabbixHost | null> {
  const resp = await rpcCall(
    apiUrl,
    'host.get',
    {
      filter: { host: ['Zabbix server'] },
      selectInterfaces: 'extend',
    },
    authToken,
  );

  if (resp.error) {
    throw new Error(`获取主机信息失败: ${resp.error.data}`);
  }

  const hosts = resp.result as ZabbixHost[];
  return hosts[0] ?? null;
}

/**
 * 修改主机接口的 Agent 连接地址
 * 将 IP 模式（127.0.0.1）切换为 DNS 模式（容器名 zabbix-agent）
 */
async function fixAgentInterface(
  apiUrl: string,
  authToken: string,
  interfaceId: string,
): Promise<boolean> {
  const resp = await rpcCall(
    apiUrl,
    'hostinterface.update',
    {
      interfaceid: interfaceId,
      useip: '0', // 使用 DNS 而非 IP
      dns: CONTAINER_NAMES.agent,
      port: '10050',
    },
    authToken,
  );

  if (resp.error) {
    throw new Error(`修改 Agent 接口失败: ${resp.error.data}`);
  }

  return true;
}

/**
 * 部署后初始化：自动修正 Zabbix 默认主机的 Agent 接口地址
 *
 * Zabbix 默认创建的 "Zabbix server" 主机，其 Agent 接口指向 127.0.0.1，
 * 在容器化部署中 Agent 运行在独立容器，需要将接口地址改为 Agent 容器的 DNS 名称。
 *
 * @param apiUrl Zabbix API 完整地址
 */
export async function postInitZabbix(apiUrl: string): Promise<PostInitResult> {
  try {
    // 1. 登录
    const authToken = await login(apiUrl);

    // 2. 获取默认主机
    const host = await getDefaultHost(apiUrl, authToken);
    if (!host) {
      return {
        success: true,
        agentInterfaceFixed: false,
        error: '未找到默认主机 "Zabbix server"，跳过接口修正',
      };
    }

    // 3. 查找 Agent 类型接口（type=1）
    const agentInterface = host.interfaces.find((iface) => iface.type === '1');
    if (!agentInterface) {
      return {
        success: true,
        agentInterfaceFixed: false,
        error: '默认主机没有 Agent 类型接口，跳过修正',
      };
    }

    // 4. 检查是否需要修正（已经是 DNS 模式且指向 Agent 容器名则跳过）
    if (agentInterface.useip === '0' && agentInterface.dns === CONTAINER_NAMES.agent) {
      return { success: true, agentInterfaceFixed: false };
    }

    // 5. 修正接口地址
    await fixAgentInterface(apiUrl, authToken, agentInterface.interfaceid);

    return { success: true, agentInterfaceFixed: true };
  } catch (error: unknown) {
    const msg = error instanceof Error ? error.message : String(error);
    return { success: false, agentInterfaceFixed: false, error: msg };
  }
}

/**
 * 等待 Zabbix API 可用（带重试）
 *
 * Zabbix Web 容器启动后，API 需要较长时间才能响应（首次部署需要初始化数据库 schema）。
 * 根据运行环境自动选择正确的 API 地址，并以指定间隔轮询直到 API 可达或超时。
 *
 * @param webPort Zabbix Web 前端端口（宿主机映射端口）
 * @returns 可用的 API URL，超时返回 null
 */
export async function waitForZabbixApi(webPort: number): Promise<string | null> {
  const apiUrl = buildApiUrl(webPort);
  const startTime = Date.now();

  while (Date.now() - startTime < API_WAIT_TIMEOUT_MS) {
    try {
      const resp = await rpcCall(apiUrl, 'apiinfo.version', {});
      if (resp.result) {
        return apiUrl;
      }
    } catch {
      // API 尚未就绪，继续等待
    }

    await Bun.sleep(API_POLL_INTERVAL_MS);
  }

  return null;
}
