package main

// ─── 版本常量 ──────────────────────────────────────────────

const AppVersion = "0.1.0"

// ─── Zabbix 镜像 ───────────────────────────────────────────

var ZabbixImages = []string{
	"postgres:16-alpine",
	"zabbix/zabbix-server-pgsql:alpine-7.0-latest",
	"zabbix/zabbix-web-nginx-pgsql:alpine-7.0-latest",
	"zabbix/zabbix-agent2:alpine-7.0-latest",
}

const SnmpTrapsImage = "zabbix/zabbix-snmptraps:alpine-7.0-latest"

var ImageLabels = map[string]string{
	"postgres:16-alpine":                              "PostgreSQL 16",
	"zabbix/zabbix-server-pgsql:alpine-7.0-latest":    "Zabbix Server",
	"zabbix/zabbix-web-nginx-pgsql:alpine-7.0-latest": "Zabbix Web (Nginx)",
	"zabbix/zabbix-agent2:alpine-7.0-latest":          "Zabbix Agent2",
	"zabbix/zabbix-snmptraps:alpine-7.0-latest":       "Zabbix SNMP Traps",
}

// ImageToTarName 将镜像名转换为 tar 文件名
// 规则：/ → -，: → -，追加 .tar
func ImageToTarName(image string) string {
	result := make([]byte, 0, len(image)+4)
	for i := 0; i < len(image); i++ {
		c := image[i]
		if c == '/' || c == ':' {
			result = append(result, '-')
		} else {
			result = append(result, c)
		}
	}
	result = append(result, '.', 't', 'a', 'r')
	return string(result)
}

// ─── 部署目录 ──────────────────────────────────────────────

const DefaultDeployDir = "/opt/zabbix"
const ComposeProjectName = "zabbix"
const ComposeFileName = "docker-compose.yml"

// ─── 容器名称 ──────────────────────────────────────────────

const (
	ContainerPostgres  = "zabbix-postgres"
	ContainerServer    = "zabbix-server"
	ContainerWeb       = "zabbix-web"
	ContainerAgent     = "zabbix-agent"
	ContainerSnmptraps = "zabbix-snmptraps"
)

// ─── 健康检查 ──────────────────────────────────────────────

const HealthCheckIntervalMs = 3000
const HealthCheckTimeoutMs = 180_000

// ─── Docker 离线安装相关常量 ──────────────────────────────

const DockerVersion = "27.5.1"
const ComposeVersion = "v2.35.1"
const DockerPackagesDir = "docker"
const DockerBinDir = "/usr/local/bin"
const DockerCLIPluginsDir = "/usr/local/lib/docker/cli-plugins"
const DockerServicePath = "/etc/systemd/system/docker.service"
const DockerSocketPath = "/var/run/docker.sock"
const ContainerdServicePath = "/etc/systemd/system/containerd.service"

var DockerBinaries = []string{
	"containerd",
	"containerd-shim-runc-v2",
	"ctr",
	"docker",
	"docker-init",
	"docker-proxy",
	"dockerd",
	"runc",
}

// ─── Docker 安装步骤 ───────────────────────────────────────

type DockerInstallStep string

const (
	StepCheckExisting   DockerInstallStep = "check-existing"
	StepExtractBinaries DockerInstallStep = "extract-binaries"
	StepCreateGroup     DockerInstallStep = "create-group"
	StepCreateService   DockerInstallStep = "create-service"
	StepStartDocker     DockerInstallStep = "start-docker"
	StepInstallCompose  DockerInstallStep = "install-compose"
	StepVerify          DockerInstallStep = "verify"
)

var DockerInstallStepLabels = map[DockerInstallStep]string{
	StepCheckExisting:   "检查现有安装",
	StepExtractBinaries: "安装 Docker 二进制文件",
	StepCreateGroup:     "创建 docker 用户组",
	StepCreateService:   "创建 systemd 服务",
	StepStartDocker:     "启动 Docker 服务",
	StepInstallCompose:  "安装 Docker Compose",
	StepVerify:          "验证安装",
}

// ─── 部署步骤 ──────────────────────────────────────────────

type DeployStep string

const (
	DeployStepPreflight       DeployStep = "preflight"
	DeployStepLoadImages      DeployStep = "load-images"
	DeployStepCreateDir       DeployStep = "create-dir"
	DeployStepGenerateCompose DeployStep = "generate-compose"
	DeployStepStartServices   DeployStep = "start-services"
	DeployStepHealthCheck     DeployStep = "health-check"
	DeployStepPostInit        DeployStep = "post-init"
)

var DeployStepMessages = map[DeployStep]string{
	DeployStepPreflight:       "检查 Docker 环境",
	DeployStepLoadImages:      "加载离线镜像",
	DeployStepCreateDir:       "创建部署目录",
	DeployStepGenerateCompose: "生成 docker-compose.yml",
	DeployStepStartServices:   "启动服务",
	DeployStepHealthCheck:     "健康检查",
	DeployStepPostInit:        "部署后初始化",
}

// ─── 清理步骤 ──────────────────────────────────────────────

type CleanupStep string

const (
	CleanupStepStopServices  CleanupStep = "stop-services"
	CleanupStepRemoveVolumes CleanupStep = "remove-volumes"
	CleanupStepRemoveImages  CleanupStep = "remove-images"
	CleanupStepRemoveDir     CleanupStep = "remove-deploy-dir"
)

var CleanupStepLabels = map[CleanupStep]string{
	CleanupStepStopServices:  "停止容器",
	CleanupStepRemoveVolumes: "清理数据卷",
	CleanupStepRemoveImages:  "清理镜像",
	CleanupStepRemoveDir:     "删除部署目录",
}

// ─── 部署配置结构 ──────────────────────────────────────────

type DatabaseConfig struct {
	Host     string
	Port     int
	Name     string
	User     string
	Password string
}

type ServerConfig struct {
	ListenPort        int
	CacheSize         string
	StartPollers      int
	EnableSnmpTrapper bool
	SnmpTrapperPort   int
}

type WebConfig struct {
	HTTPPort  int
	HTTPSPort int
	Timezone  string
}

type AgentConfig struct {
	Hostname   string
	ServerHost string
	ListenPort int
}

type DeployConfig struct {
	Version  string
	Database DatabaseConfig
	Server   ServerConfig
	Web      WebConfig
	Agent    AgentConfig
}

type DeployOptions struct {
	DeployDir          string
	PackagesDir        string
	SkipExistingImages bool
}

// DefaultDeployConfig 返回带默认值的部署配置
func DefaultDeployConfig() DeployConfig {
	return DeployConfig{
		Version: "7.0",
		Database: DatabaseConfig{
			Host: "postgres",
			Port: 5432,
			Name: "zabbix",
			User: "zabbix",
		},
		Server: ServerConfig{
			ListenPort:      10051,
			CacheSize:       "128M",
			StartPollers:    5,
			SnmpTrapperPort: 162,
		},
		Web: WebConfig{
			HTTPPort:  8080,
			HTTPSPort: 8443,
			Timezone:  "Asia/Shanghai",
		},
		Agent: AgentConfig{
			Hostname:   "Zabbix server",
			ServerHost: "zabbix-server",
			ListenPort: 10050,
		},
	}
}

// ─── Docker 检查结果 ───────────────────────────────────────

type DockerCheckResult struct {
	DockerInstalled  bool
	DockerRunning    bool
	DockerVersion    string
	ComposeInstalled bool
	ComposeVersion   string
	IsRoot           bool
	Arch             string
}

// ─── Docker 安装步骤结果 ───────────────────────────────────

type DockerInstallStepResult struct {
	Step    DockerInstallStep
	Success bool
	Message string
	Skipped bool
}

// ─── Docker 离线包扫描结果 ─────────────────────────────────

type DockerPackageScan struct {
	HasDockerTgz   bool
	DockerTgzPath  string
	DockerTgzName  string
	HasComposeBin  bool
	ComposeBinPath string
	ComposeBinName string
	DirExists      bool
}

// ─── Docker 安装结果 ───────────────────────────────────────

type DockerInstallResult struct {
	Success      bool
	Steps        []DockerInstallStepResult
	NeedsRelogin bool
}

// ─── Docker 安装回调 ───────────────────────────────────────

type DockerInstallCallbacks struct {
	OnStepStart func(step DockerInstallStep, message string)
	OnStepDone  func(step DockerInstallStep, result DockerInstallStepResult)
	OnStepError func(step DockerInstallStep, errMsg string)
}

// ─── 容器状态 ──────────────────────────────────────────────

type ContainerStatus struct {
	Name   string
	State  string
	Status string
	Health string
}

// ─── 镜像信息 ──────────────────────────────────────────────

type ImageInfo struct {
	Name string
	ID   string
	Size string
}

// ─── 镜像状态 ──────────────────────────────────────────────

type ImageStatus struct {
	Image     string
	Label     string
	TarName   string
	TarExists bool
	Loaded    bool
}

// ─── 镜像加载结果 ──────────────────────────────────────────

type LoadResult struct {
	Image   string
	Label   string
	Success bool
	Skipped bool
	Error   string
}

// ─── 健康检查结果 ──────────────────────────────────────────

type ServiceHealth struct {
	Name    string
	State   string
	Healthy bool
}

type HealthCheckResult struct {
	AllHealthy bool
	Services   []ServiceHealth
	Elapsed    int64 // milliseconds
	TimedOut   bool
}

// ─── 部署结果 ──────────────────────────────────────────────

type DeployResult struct {
	Success     bool
	HealthCheck *HealthCheckResult
	PostInit    *PostInitResult
}

// ─── 部署回调 ──────────────────────────────────────────────

type DeployCallbacks struct {
	OnStepStart     func(step DeployStep, message string)
	OnStepDone      func(step DeployStep, message string)
	OnStepError     func(step DeployStep, errMsg string)
	OnImageProgress func(result LoadResult, index int, total int)
	OnHealthTick    func(services []ServiceHealth, elapsed int64)
}

// ─── 环境状态 ──────────────────────────────────────────────

type ImageReadiness struct {
	Ready   bool
	Missing []string
}

type EnvironmentStatus struct {
	DeployDirExists   bool
	ComposeFileExists bool
	Images            ImageReadiness
	Containers        []ContainerStatus
}

// ─── 环境快照（清理前用） ──────────────────────────────────

type EnvironmentSnapshot struct {
	Containers        []ContainerStatus
	Volumes           []string
	Images            []ImageInfo
	ComposeFileExists bool
	DeployDirExists   bool
	DeployDir         string
}

// ─── 清理选项 ──────────────────────────────────────────────

type CleanupOptions struct {
	RemoveVolumes   bool
	RemoveImages    bool
	RemoveDeployDir bool
}

// ─── 清理步骤结果 ──────────────────────────────────────────

type CleanupStepResult struct {
	Step    CleanupStep
	Success bool
	Message string
	Details []string
}

// ─── 清理结果 ──────────────────────────────────────────────

type CleanupResult struct {
	Steps      []CleanupStepResult
	AllSuccess bool
}

// ─── 清理回调 ──────────────────────────────────────────────

type CleanupCallbacks struct {
	OnStepStart func(step CleanupStep, message string)
	OnStepDone  func(step CleanupStep, result CleanupStepResult)
}

// ─── Zabbix API 初始化结果 ─────────────────────────────────

type PostInitResult struct {
	Success             bool
	AgentInterfaceFixed bool
	Error               string
}

// ─── CLI Action ────────────────────────────────────────────

type Action string

const (
	ActionInstallDocker Action = "install-docker"
	ActionDeploy        Action = "deploy"
	ActionStatus        Action = "status"
	ActionStop          Action = "stop"
	ActionUninstall     Action = "uninstall"
	ActionQuit          Action = "quit"
)

// ─── CLI DeployArgs ────────────────────────────────────────

type DeployArgs struct {
	DeployDir         string
	DBPassword        string
	WebPort           int
	Timezone          string
	ServerPort        int
	CacheSize         string
	StartPollers      int
	EnableSnmpTrapper bool
	SnmpTrapperPort   int
}

// ─── ParsedArgs ────────────────────────────────────────────

type ParsedArgs struct {
	Command     *Action
	AutoConfirm bool
	Help        bool
	DeployArgs  DeployArgs
	// HasDeployArgs 为 true 表示至少有一个 deploy 参数被显式传入（与 TS 的 Object.keys(deployArgs).length > 0 等价）
	HasDeployArgs bool
}

// ─── CliContext ────────────────────────────────────────────

type CliContext struct {
	AutoConfirm bool
	DeployArgs  DeployArgs
	// HasDeployArgs 为 true 表示至少有一个 deploy 参数被显式传入
	HasDeployArgs bool
}

// ─── ComposeDownOptions ────────────────────────────────────

type ComposeDownOptions struct {
	RemoveVolumes bool
	RemoveImages  bool
}
