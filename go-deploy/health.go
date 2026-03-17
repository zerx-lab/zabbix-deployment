package main

import (
	"path/filepath"
	"time"
)

// waitForHealthy polls container health until all services are ready or timeout.
func waitForHealthy(
	deployDir string,
	onTick func(services []ServiceHealth, elapsed int64),
) HealthCheckResult {
	composeFile := filepath.Join(deployDir, ComposeFileName)
	startTime := time.Now()

	for {
		elapsed := time.Since(startTime).Milliseconds()

		// Timeout check
		if elapsed >= HealthCheckTimeoutMs {
			statuses := getComposeStatus(composeFile, ComposeProjectName)
			return HealthCheckResult{
				AllHealthy: false,
				Services:   mapToServiceHealth(statuses),
				Elapsed:    elapsed,
				TimedOut:   true,
			}
		}

		statuses := getComposeStatus(composeFile, ComposeProjectName)
		services := mapToServiceHealth(statuses)

		if onTick != nil {
			onTick(services, elapsed)
		}

		// All services ready (and at least one service exists)
		if len(services) > 0 && allHealthy(services) {
			return HealthCheckResult{
				AllHealthy: true,
				Services:   services,
				Elapsed:    elapsed,
				TimedOut:   false,
			}
		}

		// Any container has exited or died — fail fast
		for _, s := range services {
			if s.State == "exited" || s.State == "dead" {
				return HealthCheckResult{
					AllHealthy: false,
					Services:   services,
					Elapsed:    elapsed,
					TimedOut:   false,
				}
			}
		}

		time.Sleep(HealthCheckIntervalMs * time.Millisecond)
	}
}

// mapToServiceHealth converts ContainerStatus slice to ServiceHealth slice.
// A container is considered healthy when it is running AND either has a
// passing health-check ("healthy") or has no health-check defined ("").
func mapToServiceHealth(statuses []ContainerStatus) []ServiceHealth {
	services := make([]ServiceHealth, 0, len(statuses))
	for _, s := range statuses {
		healthy := s.State == "running" && (s.Health == "healthy" || s.Health == "")
		services = append(services, ServiceHealth{
			Name:    s.Name,
			State:   s.State,
			Healthy: healthy,
		})
	}
	return services
}

// allHealthy returns true when every service in the slice is healthy.
func allHealthy(services []ServiceHealth) bool {
	for _, s := range services {
		if !s.Healthy {
			return false
		}
	}
	return true
}
