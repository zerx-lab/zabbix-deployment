/**
 * 执行 shell 命令并返回结果
 * 当命令不存在时不会抛异常，而是返回 exitCode=127
 */
export async function exec(command: string[]): Promise<ExecResult> {
  try {
    const proc = Bun.spawn(command, {
      stdout: 'pipe',
      stderr: 'pipe',
    });

    const stdout = await new Response(proc.stdout).text();
    const stderr = await new Response(proc.stderr).text();
    const exitCode = await proc.exited;

    return { stdout: stdout.trim(), stderr: stderr.trim(), exitCode };
  } catch (error: unknown) {
    // Bun.spawn 在找不到可执行文件时会抛 Error
    const message = error instanceof Error ? error.message : String(error);
    return { stdout: '', stderr: message, exitCode: 127 };
  }
}

export interface ExecResult {
  stdout: string;
  stderr: string;
  exitCode: number;
}

/**
 * 检查命令是否存在
 */
export async function commandExists(cmd: string): Promise<boolean> {
  try {
    const result = await exec(['which', cmd]);
    return result.exitCode === 0;
  } catch {
    return false;
  }
}
