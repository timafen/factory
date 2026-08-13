package controlplane

import (
	"crypto/sha256"
	"embed"
	"fmt"
	"os"
	"path/filepath"
)

//go:embed report_scripts/*.mjs
var reportScripts embed.FS

func MaterializeReportScripts(root string) (capture, renderer string, err error) {
	directory := filepath.Join(root, "runtime")
	if err = os.MkdirAll(directory, 0o700); err != nil {
		return "", "", err
	}
	write := func(name string) (string, error) {
		body, readErr := reportScripts.ReadFile("report_scripts/" + name)
		if readErr != nil {
			return "", readErr
		}
		digest := fmt.Sprintf("%x", sha256.Sum256(body))[:12]
		path := filepath.Join(directory, digest+"-"+name)
		if existing, readErr := os.ReadFile(path); readErr == nil && string(existing) == string(body) {
			return path, nil
		}
		if writeErr := os.WriteFile(path, body, 0o600); writeErr != nil {
			return "", writeErr
		}
		return path, nil
	}
	if capture, err = write("capture.mjs"); err != nil {
		return "", "", err
	}
	renderer, err = write("render.mjs")
	return capture, renderer, err
}
