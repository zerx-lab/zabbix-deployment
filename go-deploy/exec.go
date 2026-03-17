package main

import (
	"bytes"
	"os/exec"
)

// ExecResult holds the result of a shell command execution
type ExecResult struct {
	Stdout   string
	Stderr   string
	ExitCode int
}

// execCmd runs a command and returns its output.
// Never panics on missing binary — returns exitCode=127 instead.
func execCmd(command []string) ExecResult {
	if len(command) == 0 {
		return ExecResult{ExitCode: 1, Stderr: "empty command"}
	}

	cmd := exec.Command(command[0], command[1:]...)

	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	err := cmd.Run()

	exitCode := 0
	if err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			exitCode = exitErr.ExitCode()
		} else {
			// Binary not found or could not be executed
			return ExecResult{
				Stdout:   "",
				Stderr:   err.Error(),
				ExitCode: 127,
			}
		}
	}

	return ExecResult{
		Stdout:   trimString(stdout.String()),
		Stderr:   trimString(stderr.String()),
		ExitCode: exitCode,
	}
}

// commandExists checks whether an executable is available in PATH.
func commandExists(cmd string) bool {
	_, err := exec.LookPath(cmd)
	return err == nil
}

// trimString trims trailing newline / whitespace from command output.
func trimString(s string) string {
	// Manual trim to avoid importing strings at this level
	end := len(s)
	for end > 0 && (s[end-1] == '\n' || s[end-1] == '\r' || s[end-1] == ' ' || s[end-1] == '\t') {
		end--
	}
	return s[:end]
}
