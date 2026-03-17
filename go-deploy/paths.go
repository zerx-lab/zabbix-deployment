package main

import (
	"os"
	"path/filepath"
	"strings"
)

// getPackagesDir returns the path to the packages/ directory.
//
// Strategy (mirrors TypeScript getPackagesDir logic):
//  1. If the executable is a real compiled binary (not the Go toolchain itself),
//     look for packages/ next to the executable.
//  2. Fall back to cwd/packages — covers `go run .` development mode and any
//     case where the binary is invoked from the project root.
func getPackagesDir() string {
	execPath, err := os.Executable()
	if err == nil {
		execPath = resolveSymlink(execPath)
		base := filepath.Base(execPath)
		// Go toolchain binaries are named "go", compiled test binaries contain
		// ".test", and `go run` uses a temp path. Treat everything else as a
		// real compiled binary.
		if base != "go" && !strings.HasSuffix(base, ".test") && !strings.Contains(execPath, "/go-build") {
			candidate := filepath.Join(filepath.Dir(execPath), "packages")
			if dirExists(candidate) {
				return candidate
			}
		}
	}

	// Development / fallback: use current working directory
	cwd, err := os.Getwd()
	if err != nil {
		cwd = "."
	}
	return filepath.Join(cwd, "packages")
}

// resolveSymlink attempts to resolve symlinks on the executable path.
// Returns the original path if resolution fails.
func resolveSymlink(path string) string {
	resolved, err := filepath.EvalSymlinks(path)
	if err != nil {
		return path
	}
	return resolved
}

// dirExists returns true if the given path exists and is a directory.
func dirExists(path string) bool {
	info, err := os.Stat(path)
	if err != nil {
		return false
	}
	return info.IsDir()
}

// fileExists returns true if the given path exists and is a regular file.
func fileExists(path string) bool {
	info, err := os.Stat(path)
	if err != nil {
		return false
	}
	return !info.IsDir()
}
