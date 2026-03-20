package main

import (
	"fmt"
	"os"
	"strconv"
)

// ─── 帮助文本 ──────────────────────────────────────────────

const helpText = `Zabbix 离线部署工具

用法: zabbix-deploy [命令] [选项]

命令:
  install-docker       安装 Docker（从离线包）
  deploy               部署 Zabbix
  status               检查服务状态
  stop                 停止服务
  uninstall            彻底清理
  import-templates     将内嵌的 Zabbix 监控模板导入到指定 Zabbix 实例
  list-templates       列出二进制中内嵌的所有监控模板
  create-dashboard     在 Zabbix 中创建「服务器硬件巡检总览」仪表盘

通用选项:
  -y, --yes            自动确认所有操作（跳过确认提示）
  -h, --help           显示帮助信息

Deploy 选项:
  --deploy-dir <path>        部署目录（默认 /opt/zabbix）
  --db-password <password>   数据库密码（必填，至少 8 位）
  --web-port <port>          Web 访问端口（默认 8080）
  --timezone <tz>            时区（默认 Asia/Shanghai）
  --server-port <port>       Server 监听端口（默认 10051）
  --cache-size <size>        缓存大小（默认 128M）
  --start-pollers <n>        Poller 数量（默认 5）
  --enable-snmp-trapper      启用 SNMP Trap 接收
  --snmp-trapper-port <port> SNMP Trap 端口（默认 162）

Import-Templates 选项:
  --api-url <url>            Zabbix API 完整地址
                             例如: http://192.168.1.10:8080/api_jsonrpc.php
                             若不指定则根据 --web-port 自动构建（指向 localhost）
  --web-port <port>          Zabbix Web 端口（当 --api-url 未指定时使用，默认 8080）
  --zabbix-user <user>       Zabbix 登录用户名（默认 Admin）
  --zabbix-password <pass>   Zabbix 登录密码（默认 zabbix）
  --force                    强制覆盖已存在的模板（默认：已存在则跳过）

Create-Dashboard 选项:
  --api-url <url>            Zabbix API 完整地址
                             例如: http://192.168.1.10:8080/api_jsonrpc.php
                             若不指定则根据 --web-port 自动构建（指向 localhost）
  --web-port <port>          Zabbix Web 端口（当 --api-url 未指定时使用，默认 8080）
  --zabbix-user <user>       Zabbix 登录用户名（默认 Admin）
  --zabbix-password <pass>   Zabbix 登录密码（默认 zabbix）
  --force                    若仪表盘已存在则删除重建（默认：已存在则跳过）

示例:
  # 交互式 TUI 模式
  ./zabbix-deploy

  # 直接安装 Docker（自动确认）
  ./zabbix-deploy install-docker -y

  # 查看状态
  ./zabbix-deploy status

  # 部署 Zabbix（CLI 模式）
  ./zabbix-deploy deploy -y --db-password mypassword123

  # 停止服务（自动确认）
  ./zabbix-deploy stop -y

  # 彻底清理（自动确认）
  ./zabbix-deploy uninstall -y

  # 列出内嵌模板
  ./zabbix-deploy list-templates

  # 导入模板到本机部署的 Zabbix（默认端口 8080）
  ./zabbix-deploy import-templates

  # 导入模板到指定 Zabbix（自定义地址和凭据）
  ./zabbix-deploy import-templates --api-url http://192.168.1.10:8080/api_jsonrpc.php --zabbix-user Admin --zabbix-password mypassword

  # 导入模板并强制覆盖已有对象
  ./zabbix-deploy import-templates --force

  # 创建服务器硬件巡检总览仪表盘（默认端口 8080）
  ./zabbix-deploy create-dashboard

  # 创建仪表盘到指定 Zabbix 实例
  ./zabbix-deploy create-dashboard --api-url http://192.168.1.10:8080/api_jsonrpc.php

  # 若仪表盘已存在则强制删除重建
  ./zabbix-deploy create-dashboard --force`

// showHelp 打印帮助信息
func showHelp() {
	fmt.Println(helpText)
}

// ─── 有效命令集 ────────────────────────────────────────────

var validCommands = map[string]Action{
	"install-docker":   ActionInstallDocker,
	"deploy":           ActionDeploy,
	"status":           ActionStatus,
	"stop":             ActionStop,
	"uninstall":        ActionUninstall,
	"import-templates": ActionImportTemplates,
	"list-templates":   ActionListTemplates,
	"create-dashboard": ActionCreateDashboard,
}

// ─── parseArgs 解析命令行参数 ──────────────────────────────

// parseArgs parses os.Args[1:] and returns a ParsedArgs struct.
// On error it prints a message and calls os.Exit(1).
func parseArgs(argv []string) ParsedArgs {
	// skip program name
	args := argv[1:]

	result := ParsedArgs{
		Command:     nil,
		AutoConfirm: false,
		Help:        false,
		DeployArgs: DeployArgs{
			WebPort:         8080,
			Timezone:        "Asia/Shanghai",
			ServerPort:      10051,
			CacheSize:       "128M",
			StartPollers:    5,
			SnmpTrapperPort: 162,
			DeployDir:       DefaultDeployDir,
		},
		ImportTemplatesArgs: ImportTemplatesArgs{
			WebPort:  8080,
			Username: defaultZabbixUsername,
			Password: defaultZabbixPassword,
			Force:    false,
		},
		CreateDashboardArgs: CreateDashboardArgs{
			WebPort:  8080,
			Username: defaultZabbixUsername,
			Password: defaultZabbixPassword,
			Force:    false,
		},
	}

	i := 0
	for i < len(args) {
		arg := args[i]

		// ── 子命令 ───────────────────────────────────────
		if !isFlag(arg) && result.Command == nil {
			action, ok := validCommands[arg]
			if !ok {
				fmt.Fprintf(os.Stderr, "未知命令: %s\n", arg)
				fmt.Fprintln(os.Stderr, "使用 --help 查看可用命令")
				os.Exit(1)
			}
			result.Command = &action
			i++
			continue
		}

		// ── 标志 / 选项 ───────────────────────────────────
		switch arg {
		case "-y", "--yes":
			result.AutoConfirm = true

		case "-h", "--help":
			result.Help = true

		// ── deploy 专属选项 ───────────────────────────────
		case "--deploy-dir":
			result.DeployArgs.DeployDir = requireValue(args, i, arg)
			result.HasDeployArgs = true
			i++

		case "--db-password":
			result.DeployArgs.DBPassword = requireValue(args, i, arg)
			result.HasDeployArgs = true
			i++

		case "--timezone":
			result.DeployArgs.Timezone = requireValue(args, i, arg)
			result.HasDeployArgs = true
			i++

		case "--server-port":
			result.DeployArgs.ServerPort = requirePort(args, i, arg)
			result.HasDeployArgs = true
			i++

		case "--cache-size":
			result.DeployArgs.CacheSize = requireValue(args, i, arg)
			result.HasDeployArgs = true
			i++

		case "--start-pollers":
			val := requireValue(args, i, arg)
			n, err := strconv.Atoi(val)
			if err != nil || n < 1 || n > 100 {
				fmt.Fprintf(os.Stderr, "%s 值无效: %s（应为 1-100 之间的数字）\n", arg, val)
				os.Exit(1)
			}
			result.DeployArgs.StartPollers = n
			result.HasDeployArgs = true
			i++

		case "--enable-snmp-trapper":
			result.DeployArgs.EnableSnmpTrapper = true
			result.HasDeployArgs = true

		case "--snmp-trapper-port":
			result.DeployArgs.SnmpTrapperPort = requirePort(args, i, arg)
			result.HasDeployArgs = true
			i++

		// ── 共用选项（deploy + import-templates + create-dashboard 均可使用） ─
		case "--web-port":
			port := requirePort(args, i, arg)
			result.DeployArgs.WebPort = port
			result.ImportTemplatesArgs.WebPort = port
			result.CreateDashboardArgs.WebPort = port
			result.HasDeployArgs = true
			i++

		// ── import-templates / create-dashboard 共用选项 ──
		case "--api-url":
			val := requireValue(args, i, arg)
			result.ImportTemplatesArgs.APIURL = val
			result.CreateDashboardArgs.APIURL = val
			i++

		case "--zabbix-user":
			val := requireValue(args, i, arg)
			result.ImportTemplatesArgs.Username = val
			result.CreateDashboardArgs.Username = val
			i++

		case "--zabbix-password":
			val := requireValue(args, i, arg)
			result.ImportTemplatesArgs.Password = val
			result.CreateDashboardArgs.Password = val
			i++

		case "--force":
			result.ImportTemplatesArgs.Force = true
			result.CreateDashboardArgs.Force = true

		default:
			fmt.Fprintf(os.Stderr, "未知选项: %s\n", arg)
			fmt.Fprintln(os.Stderr, "使用 --help 查看可用选项")
			os.Exit(1)
		}

		i++
	}

	return result
}

// ─── 辅助函数 ──────────────────────────────────────────────

// isFlag returns true if the argument starts with '-'.
func isFlag(s string) bool {
	return len(s) > 0 && s[0] == '-'
}

// requireValue reads the next argument as a string value.
// Exits with an error if the next argument is missing or starts with '-'.
func requireValue(args []string, index int, flag string) string {
	if index+1 >= len(args) || isFlag(args[index+1]) {
		fmt.Fprintf(os.Stderr, "%s 需要一个值\n", flag)
		os.Exit(1)
	}
	return args[index+1]
}

// requirePort reads the next argument as a valid port number (1-65535).
// Exits with an error on invalid input.
func requirePort(args []string, index int, flag string) int {
	val := requireValue(args, index, flag)
	port, err := strconv.Atoi(val)
	if err != nil || port < 1 || port > 65535 {
		fmt.Fprintf(os.Stderr, "%s 端口号无效: %s（应为 1-65535）\n", flag, val)
		os.Exit(1)
	}
	return port
}
