package main

import (
	"errors"
	"fmt"
	"strconv"
	"strings"

	"github.com/charmbracelet/huh"
)

// collectDeployConfig 通过 TUI 交互收集部署配置
// 返回 nil 表示用户取消了操作
func collectDeployConfig() (*struct {
	Config  DeployConfig
	Options DeployOptions
}, error) {
	cfg := DefaultDeployConfig()

	// ── 基础配置 ──────────────────────────────────────────

	deployDir := DefaultDeployDir
	dbPassword := ""
	webPortStr := "8080"
	timezone := "Asia/Shanghai"

	basicForm := huh.NewForm(
		huh.NewGroup(
			huh.NewInput().
				Title("部署目录（存放 compose 文件和数据卷）").
				Placeholder(DefaultDeployDir).
				Value(&deployDir).
				Validate(func(s string) error {
					if s == "" {
						s = DefaultDeployDir
					}
					if !strings.HasPrefix(s, "/") {
						return errors.New("请输入绝对路径")
					}
					return nil
				}),

			huh.NewInput().
				Title("数据库密码（至少 8 位）").
				EchoMode(huh.EchoModePassword).
				Value(&dbPassword).
				Validate(func(s string) error {
					if len(s) < 8 {
						return errors.New("密码至少 8 位")
					}
					return nil
				}),

			huh.NewInput().
				Title("Web 访问端口").
				Placeholder("8080").
				Value(&webPortStr).
				Validate(func(s string) error {
					if s == "" {
						return nil
					}
					port, err := strconv.Atoi(s)
					if err != nil || port < 1 || port > 65535 {
						return errors.New("请输入有效端口号 (1-65535)")
					}
					return nil
				}),

			huh.NewInput().
				Title("时区").
				Placeholder("Asia/Shanghai").
				Value(&timezone),
		),
	)

	if err := basicForm.Run(); err != nil {
		if errors.Is(err, huh.ErrUserAborted) {
			printCancel("操作已取消")
			return nil, nil
		}
		return nil, fmt.Errorf("收集基础配置失败: %w", err)
	}

	// 处理默认值
	if deployDir == "" {
		deployDir = DefaultDeployDir
	}
	if webPortStr == "" {
		webPortStr = "8080"
	}
	if timezone == "" {
		timezone = "Asia/Shanghai"
	}
	webPort, _ := strconv.Atoi(webPortStr)
	if webPort == 0 {
		webPort = 8080
	}

	// ── 高级配置确认 ──────────────────────────────────────

	advancedMode := false
	advConfirm := huh.NewForm(
		huh.NewGroup(
			huh.NewConfirm().
				Title("是否配置高级选项？（Server 缓存、Poller 数量等）").
				Value(&advancedMode),
		),
	)
	if err := advConfirm.Run(); err != nil {
		if errors.Is(err, huh.ErrUserAborted) {
			printCancel("操作已取消")
			return nil, nil
		}
		return nil, fmt.Errorf("收集高级配置确认失败: %w", err)
	}

	// ── 高级配置 ──────────────────────────────────────────

	cacheSize := "128M"
	pollersStr := "5"
	serverPortStr := "10051"
	enableSnmpTrapper := false
	snmpPortStr := "162"

	if advancedMode {
		advForm := huh.NewForm(
			huh.NewGroup(
				huh.NewSelect[string]().
					Title("Zabbix Server 缓存大小").
					Options(
						huh.NewOption("64M（小规模）", "64M"),
						huh.NewOption("128M（默认）", "128M"),
						huh.NewOption("256M（中规模）", "256M"),
						huh.NewOption("512M（大规模）", "512M"),
						huh.NewOption("1G（超大规模）", "1G"),
					).
					Value(&cacheSize),

				huh.NewInput().
					Title("Poller 进程数").
					Placeholder("5").
					Value(&pollersStr).
					Validate(func(s string) error {
						if s == "" {
							return nil
						}
						n, err := strconv.Atoi(s)
						if err != nil || n < 1 || n > 100 {
							return errors.New("请输入 1-100 之间的数字")
						}
						return nil
					}),

				huh.NewInput().
					Title("Zabbix Server 监听端口").
					Placeholder("10051").
					Value(&serverPortStr).
					Validate(validatePort),

				huh.NewConfirm().
					Title("是否启用 SNMP Trap 接收？（用于接收网络设备主动上报的 SNMP Trap 消息）").
					Value(&enableSnmpTrapper),
			),
		)

		if err := advForm.Run(); err != nil {
			if errors.Is(err, huh.ErrUserAborted) {
				printCancel("操作已取消")
				return nil, nil
			}
			return nil, fmt.Errorf("收集高级配置失败: %w", err)
		}

		// SNMP Trap 端口（仅在启用时询问）
		if enableSnmpTrapper {
			snmpForm := huh.NewForm(
				huh.NewGroup(
					huh.NewInput().
						Title("SNMP Trap 监听端口 (UDP)").
						Placeholder("162").
						Value(&snmpPortStr).
						Validate(validatePort),
				),
			)
			if err := snmpForm.Run(); err != nil {
				if errors.Is(err, huh.ErrUserAborted) {
					printCancel("操作已取消")
					return nil, nil
				}
				return nil, fmt.Errorf("收集 SNMP 配置失败: %w", err)
			}
		}
	}

	// ── 解析高级参数 ──────────────────────────────────────

	if pollersStr == "" {
		pollersStr = "5"
	}
	startPollers, _ := strconv.Atoi(pollersStr)
	if startPollers == 0 {
		startPollers = 5
	}

	if serverPortStr == "" {
		serverPortStr = "10051"
	}
	serverPort, _ := strconv.Atoi(serverPortStr)
	if serverPort == 0 {
		serverPort = 10051
	}

	if snmpPortStr == "" {
		snmpPortStr = "162"
	}
	snmpPort, _ := strconv.Atoi(snmpPortStr)
	if snmpPort == 0 {
		snmpPort = 162
	}

	// ── 组装配置 ──────────────────────────────────────────

	cfg.Database.Password = dbPassword
	cfg.Server.ListenPort = serverPort
	cfg.Server.CacheSize = cacheSize
	cfg.Server.StartPollers = startPollers
	cfg.Server.EnableSnmpTrapper = enableSnmpTrapper
	cfg.Server.SnmpTrapperPort = snmpPort
	cfg.Web.HTTPPort = webPort
	cfg.Web.Timezone = timezone

	options := DeployOptions{
		DeployDir:          deployDir,
		SkipExistingImages: true,
	}

	return &struct {
		Config  DeployConfig
		Options DeployOptions
	}{Config: cfg, Options: options}, nil
}

// ─── 验证辅助 ──────────────────────────────────────────────

// validatePort 验证字符串是否为合法端口号
func validatePort(s string) error {
	if s == "" {
		return nil
	}
	port, err := strconv.Atoi(s)
	if err != nil || port < 1 || port > 65535 {
		return errors.New("请输入有效端口号 (1-65535)")
	}
	return nil
}
