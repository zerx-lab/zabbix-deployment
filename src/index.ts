import { intro, outro } from '@clack/prompts';
import { isTTY, parseArgs, showHelp } from './cli/args.ts';
import { runAction, runCli } from './cli/main.ts';
import { APP_VERSION } from './types/constants.ts';

async function main(): Promise<void> {
  const parsed = parseArgs(process.argv);

  // --help
  if (parsed.help) {
    showHelp();
    return;
  }

  // 有子命令 → CLI 模式（直接执行，不需要 TTY）
  if (parsed.command) {
    console.log(`Zabbix 离线部署工具 v${APP_VERSION}\n`);
    await runAction(parsed.command, {
      autoConfirm: parsed.autoConfirm,
      deployArgs: parsed.deployArgs,
    });
    return;
  }

  // 无子命令 → 交互式 TUI 模式
  if (!isTTY()) {
    console.error('错误: 当前不是交互式终端，无法启动 TUI 模式。');
    console.error('请使用子命令模式，例如:');
    console.error('  ./zabbix-deploy install-docker -y');
    console.error('  ./zabbix-deploy status');
    console.error('  ./zabbix-deploy --help');
    process.exit(1);
  }

  intro(`Zabbix 离线部署工具 v${APP_VERSION}`);
  await runCli();
  outro('再见！');
}

main().catch((error: unknown) => {
  if (error instanceof Error) {
    console.error(error.message);
  }
  process.exit(1);
});
