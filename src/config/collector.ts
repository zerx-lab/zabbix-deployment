import { cancel, confirm, isCancel, password, select, text } from '@clack/prompts';
import type { DeployConfig, DeployOptions } from '../types/config.ts';
import { DEFAULT_DEPLOY_DIR } from '../types/constants.ts';

/**
 * 通过 TUI 交互收集部署配置
 */
export async function collectDeployConfig(): Promise<{
  config: DeployConfig;
  options: DeployOptions;
} | null> {
  // 部署目录
  const deployDir = await text({
    message: '部署目录（存放 compose 文件和数据卷）:',
    placeholder: DEFAULT_DEPLOY_DIR,
    defaultValue: DEFAULT_DEPLOY_DIR,
    validate(value) {
      if (!value.startsWith('/')) return '请输入绝对路径';
    },
  });
  if (isCancel(deployDir)) {
    cancel('操作已取消');
    return null;
  }

  // 数据库密码
  const dbPassword = await password({
    message: '数据库密码（至少 8 位）:',
    validate(value) {
      if (value.length < 8) return '密码至少 8 位';
    },
  });
  if (isCancel(dbPassword)) {
    cancel('操作已取消');
    return null;
  }

  // Web 端口
  const webPort = await text({
    message: 'Web 访问端口:',
    placeholder: '8080',
    defaultValue: '8080',
    validate(value) {
      const port = Number(value);
      if (Number.isNaN(port) || port < 1 || port > 65535) return '请输入有效端口号 (1-65535)';
    },
  });
  if (isCancel(webPort)) {
    cancel('操作已取消');
    return null;
  }

  // 时区
  const timezone = await text({
    message: '时区:',
    placeholder: 'Asia/Shanghai',
    defaultValue: 'Asia/Shanghai',
  });
  if (isCancel(timezone)) {
    cancel('操作已取消');
    return null;
  }

  // 高级配置
  const advancedMode = await confirm({
    message: '是否配置高级选项？（Server 缓存、Poller 数量等）',
    initialValue: false,
  });
  if (isCancel(advancedMode)) {
    cancel('操作已取消');
    return null;
  }

  let cacheSize = '128M';
  let startPollers = 5;
  let serverPort = 10051;

  if (advancedMode) {
    const cacheSizeInput = await select({
      message: 'Zabbix Server 缓存大小:',
      options: [
        { value: '64M', label: '64M（小规模）' },
        { value: '128M', label: '128M（默认）' },
        { value: '256M', label: '256M（中规模）' },
        { value: '512M', label: '512M（大规模）' },
        { value: '1G', label: '1G（超大规模）' },
      ],
      initialValue: '128M',
    });
    if (isCancel(cacheSizeInput)) {
      cancel('操作已取消');
      return null;
    }
    cacheSize = cacheSizeInput;

    const pollersInput = await text({
      message: 'Poller 进程数:',
      placeholder: '5',
      defaultValue: '5',
      validate(value) {
        const n = Number(value);
        if (Number.isNaN(n) || n < 1 || n > 100) return '请输入 1-100 之间的数字';
      },
    });
    if (isCancel(pollersInput)) {
      cancel('操作已取消');
      return null;
    }
    startPollers = Number(pollersInput);

    const serverPortInput = await text({
      message: 'Zabbix Server 监听端口:',
      placeholder: '10051',
      defaultValue: '10051',
      validate(value) {
        const port = Number(value);
        if (Number.isNaN(port) || port < 1 || port > 65535) return '请输入有效端口号 (1-65535)';
      },
    });
    if (isCancel(serverPortInput)) {
      cancel('操作已取消');
      return null;
    }
    serverPort = Number(serverPortInput);
  }

  const config: DeployConfig = {
    version: '7.0',
    database: {
      host: 'postgres',
      port: 5432,
      name: 'zabbix',
      user: 'zabbix',
      password: dbPassword,
    },
    server: {
      listenPort: serverPort,
      cacheSize,
      startPollers,
    },
    web: {
      httpPort: Number(webPort),
      httpsPort: 8443,
      timezone: timezone,
    },
    agent: {
      hostname: 'zabbix-agent',
      serverHost: 'zabbix-server',
      listenPort: 10050,
    },
  };

  const options: DeployOptions = {
    deployDir: deployDir,
    skipExistingImages: true,
  };

  return { config, options };
}
