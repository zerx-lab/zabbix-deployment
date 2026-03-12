import { dirname, resolve } from 'node:path';

/**
 * 获取 packages 目录路径
 *
 * 编译后的二进制通过 process.argv[0] 定位同级 packages/ 目录；
 * 开发模式通过脚本路径定位项目根目录下的 packages/。
 */
export function getPackagesDir(): string {
  // Bun 编译后的二进制: process.argv[0]='bun', argv[1]='/$bunfs/...'
  // 此时用 process.execPath 获取真实二进制路径
  const realExecPath = process.execPath;

  // 如果 execPath 指向真实文件（编译后的二进制），packages 和它在同一目录
  if (realExecPath && !realExecPath.endsWith('/bun') && !realExecPath.endsWith('/bun.exe')) {
    return resolve(dirname(realExecPath), 'packages');
  }

  // 开发模式（bun run src/index.ts）：从项目根目录找 packages
  // 直接使用 cwd，因为开发时一般在项目根目录运行
  return resolve(process.cwd(), 'packages');
}
