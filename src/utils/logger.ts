export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

const LOG_LEVELS: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
};

let currentLevel: LogLevel = 'info';

export function setLogLevel(level: LogLevel): void {
  currentLevel = level;
}

function shouldLog(level: LogLevel): boolean {
  return LOG_LEVELS[level] >= LOG_LEVELS[currentLevel];
}

export const logger = {
  debug(_msg: string, ..._args: unknown[]): void {
    if (shouldLog('debug')) {
    }
  },

  info(_msg: string, ..._args: unknown[]): void {
    if (shouldLog('info')) {
    }
  },

  warn(_msg: string, ..._args: unknown[]): void {
    if (shouldLog('warn')) {
    }
  },

  error(_msg: string, ..._args: unknown[]): void {
    if (shouldLog('error')) {
    }
  },

  success(_msg: string, ..._args: unknown[]): void {},
};
