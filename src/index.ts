import { intro, outro } from '@clack/prompts';
import { runCli } from './cli/main.ts';
import { APP_VERSION } from './types/constants.ts';

async function main(): Promise<void> {
  intro(`Zabbix 离线部署工具 v${APP_VERSION}`);

  await runCli();

  outro('再见！');
}

main().catch((error: unknown) => {
  if (error instanceof Error) {
  } else {
  }
  process.exit(1);
});
