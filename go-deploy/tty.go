package main

import (
	"fmt"
	"os"
	"sync"
	"time"

	"github.com/fatih/color"
	"golang.org/x/term"
)

// ─── TTY 检测 ──────────────────────────────────────────────

// isTTY 检查当前标准输入是否为交互式终端
func isTTY() bool {
	return term.IsTerminal(int(os.Stdin.Fd()))
}

// ─── Spinner（进度指示器） ─────────────────────────────────

var spinnerFrames = []string{"⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"}

type Progress struct {
	mu      sync.Mutex
	msg     string
	stopCh  chan struct{}
	doneCh  chan struct{}
	running bool
}

func newProgress() *Progress {
	return &Progress{}
}

// Start 启动进度指示器，显示 msg
func (p *Progress) Start(msg string) {
	if !isTTY() {
		fmt.Printf("... %s\n", msg)
		return
	}

	p.mu.Lock()
	defer p.mu.Unlock()

	if p.running {
		p.msg = msg
		return
	}

	p.msg = msg
	p.stopCh = make(chan struct{})
	p.doneCh = make(chan struct{})
	p.running = true

	go func() {
		i := 0
		for {
			select {
			case <-p.stopCh:
				close(p.doneCh)
				return
			default:
				p.mu.Lock()
				currentMsg := p.msg
				p.mu.Unlock()
				fmt.Printf("\r%s %s  ", spinnerFrames[i%len(spinnerFrames)], currentMsg)
				time.Sleep(80 * time.Millisecond)
				i++
			}
		}
	}()
}

// Message 更新进度指示器的当前消息
func (p *Progress) Message(msg string) {
	if !isTTY() {
		return
	}
	p.mu.Lock()
	p.msg = msg
	p.mu.Unlock()
}

// Stop 停止进度指示器并打印最终消息
func (p *Progress) Stop(msg string) {
	if !isTTY() {
		fmt.Println(msg)
		return
	}

	p.mu.Lock()
	wasRunning := p.running
	if wasRunning {
		p.running = false
		close(p.stopCh)
	}
	p.mu.Unlock()

	if wasRunning {
		<-p.doneCh
	}

	// 清除当前行并打印最终消息
	fmt.Printf("\r\033[K%s\n", msg)
}

// ─── 日志函数（兼容 TTY / 非 TTY） ────────────────────────

var (
	colorGreen  = color.New(color.FgGreen)
	colorRed    = color.New(color.FgRed)
	colorYellow = color.New(color.FgYellow)
	colorCyan   = color.New(color.FgCyan)
	colorBold   = color.New(color.Bold)
	colorDim    = color.New(color.Faint)
)

func logInfo(msg string) {
	fmt.Println(msg)
}

func logSuccess(msg string) {
	colorGreen.Println(msg)
}

func logError(msg string) {
	colorRed.Fprintln(os.Stderr, msg)
}

func logWarn(msg string) {
	colorYellow.Println(msg)
}

func logNote(msg string, title string) {
	if isTTY() {
		fmt.Printf("\n┌─ %s\n", colorBold.Sprint(title))
		for _, line := range splitLines(msg) {
			fmt.Printf("│  %s\n", line)
		}
		fmt.Println("└─")
	} else {
		fmt.Printf("\n── %s ──\n", title)
		fmt.Println(msg)
		fmt.Println()
	}
}

// ─── intro / outro（程序启动/结束横幅） ───────────────────

func printIntro(title string) {
	if isTTY() {
		fmt.Println()
		colorBold.Printf("◆  %s\n", title)
		fmt.Println()
	} else {
		fmt.Printf("%s\n\n", title)
	}
}

func printOutro(msg string) {
	if isTTY() {
		fmt.Println()
		colorGreen.Printf("◆  %s\n", msg)
		fmt.Println()
	} else {
		fmt.Printf("\n%s\n", msg)
	}
}

// ─── 取消提示 ──────────────────────────────────────────────

func printCancel(msg string) {
	colorYellow.Printf("\n◆  %s\n\n", msg)
}

// ─── 辅助函数 ──────────────────────────────────────────────

// splitLines 将多行字符串拆分为切片
func splitLines(s string) []string {
	var lines []string
	start := 0
	for i := 0; i < len(s); i++ {
		if s[i] == '\n' {
			lines = append(lines, s[start:i])
			start = i + 1
		}
	}
	if start <= len(s) {
		lines = append(lines, s[start:])
	}
	return lines
}

// formatBool 将布尔值格式化为彩色是/否
func formatBool(b bool, trueLabel, falseLabel string) string {
	if b {
		return colorGreen.Sprint(trueLabel)
	}
	return colorRed.Sprint(falseLabel)
}

// checkMark 返回彩色对勾或叉号
func checkMark(ok bool) string {
	if ok {
		return colorGreen.Sprint("✓")
	}
	return colorRed.Sprint("✗")
}

// bulletIcon 返回彩色圆点（运行/停止状态）
func bulletIcon(running bool) string {
	if running {
		return colorGreen.Sprint("●")
	}
	return colorRed.Sprint("●")
}

// dimText 返回暗色文本
func dimText(s string) string {
	return colorDim.Sprint(s)
}

// boldText 返回粗体文本
func boldText(s string) string {
	return colorBold.Sprint(s)
}

// greenText 返回绿色文本
func greenText(s string) string {
	return colorGreen.Sprint(s)
}

// redText 返回红色文本
func redText(s string) string {
	return colorRed.Sprint(s)
}

// yellowText 返回黄色文本
func yellowText(s string) string {
	return colorYellow.Sprint(s)
}

// cyanText 返回青色文本
func cyanText(s string) string {
	return colorCyan.Sprint(s)
}
