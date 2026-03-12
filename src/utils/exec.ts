/**
 * 执行 shell 命令并返回结果
 */
export async function exec(command: string[]): Promise<ExecResult> {
  const proc = Bun.spawn(command, {
    stdout: 'pipe',
    stderr: 'pipe',
  });

  const stdout = await new Response(proc.stdout).text();
  const stderr = await new Response(proc.stderr).text();
  const exitCode = await proc.exited;

  return { stdout: stdout.trim(), stderr: stderr.trim(), exitCode };
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
