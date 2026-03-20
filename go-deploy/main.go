package main

import (
	"fmt"
	"os"
)

func main() {
	parsed := parseArgs(os.Args)

	// --help
	if parsed.Help {
		showHelp()
		return
	}

	// 有子命令 → CLI 模式（直接执行，不需要 TTY）
	if parsed.Command != nil {
		fmt.Printf("Zabbix 离线部署工具 v%s\n\n", AppVersion)
		ctx := CliContext{
			AutoConfirm:         parsed.AutoConfirm,
			DeployArgs:          parsed.DeployArgs,
			HasDeployArgs:       parsed.HasDeployArgs,
			ImportTemplatesArgs: parsed.ImportTemplatesArgs,
		}
		runAction(*parsed.Command, ctx)
		return
	}

	// 无子命令 → 交互式 TUI 模式
	if !isTTY() {
		fmt.Fprintln(os.Stderr, "错误: 当前不是交互式终端，无法启动 TUI 模式。")
		fmt.Fprintln(os.Stderr, "请使用子命令模式，例如:")
		fmt.Fprintln(os.Stderr, "  ./zabbix-deploy install-docker -y")
		fmt.Fprintln(os.Stderr, "  ./zabbix-deploy status")
		fmt.Fprintln(os.Stderr, "  ./zabbix-deploy --help")
		os.Exit(1)
	}

	printIntro(fmt.Sprintf("Zabbix 离线部署工具 v%s", AppVersion))
	runCli()
	printOutro("再见！")
}
