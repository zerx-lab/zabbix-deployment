import { describe, expect, it } from 'bun:test';
import { commandExists, exec } from '../../src/utils/exec.ts';

describe('exec', () => {
  it('should execute a simple command', async () => {
    const result = await exec(['echo', 'hello']);
    expect(result.exitCode).toBe(0);
    expect(result.stdout).toBe('hello');
  });

  it('should return non-zero exit code for failed command', async () => {
    const result = await exec(['false']);
    expect(result.exitCode).not.toBe(0);
  });
});

describe('commandExists', () => {
  it('should return true for existing command', async () => {
    const exists = await commandExists('echo');
    expect(exists).toBe(true);
  });

  it('should return false for non-existing command', async () => {
    const exists = await commandExists('nonexistent_command_xyz');
    expect(exists).toBe(false);
  });
});
