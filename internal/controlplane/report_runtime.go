package controlplane

import (
	"context"
	"crypto/sha256"
	"embed"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

const (
	DefaultReportBrowserLauncher = "/usr/local/libexec/factory/factory-browser-sandbox"
	DefaultReportBrowserRoot     = "/usr/local/libexec/factory/browser-runtime"
)

// ReportBrowserRuntime is the single installed browser entry point shared by
// visual capture and PDF rendering. The server validates it before starting
// either background service and passes it explicitly to every Node process.
type ReportBrowserRuntime struct {
	Launcher string
	Root     string
}

func NewReportBrowserRuntime(launcher, root string) ReportBrowserRuntime {
	if launcher == "" {
		launcher = DefaultReportBrowserLauncher
	}
	if root == "" {
		root = DefaultReportBrowserRoot
	}
	return ReportBrowserRuntime{Launcher: launcher, Root: root}
}

func (runtime ReportBrowserRuntime) Check(ctx context.Context) error {
	if !filepath.IsAbs(runtime.Launcher) || !filepath.IsAbs(runtime.Root) {
		return fmt.Errorf("browser launcher and runtime paths must be absolute")
	}
	info, err := os.Stat(runtime.Launcher)
	if err != nil || !info.Mode().IsRegular() || info.Mode().Perm()&0o111 == 0 {
		return fmt.Errorf("browser launcher is not an executable regular file: %s", runtime.Launcher)
	}
	packageJSON := filepath.Join(runtime.Root, "package.json")
	if info, err = os.Stat(packageJSON); err != nil || !info.Mode().IsRegular() {
		return fmt.Errorf("browser runtime package is not installed: %s", packageJSON)
	}
	probe := `const {createRequire}=require("node:module");const p=require("node:path");const r=createRequire(p.join(process.argv[1],"package.json"));const {chromium}=r("playwright");const launcher=process.argv[2];(async()=>{if(!chromium||typeof chromium.launch!=="function")throw new Error("missing Chromium launcher");const browser=await chromium.launch({headless:true,executablePath:launcher,chromiumSandbox:true});try{const page=await browser.newPage();await page.setContent("<!doctype html><title>Factory browser probe</title>");const title=await page.title();if(title!=="Factory browser probe")throw new Error("browser render probe failed");await page.close()}finally{await browser.close()}})().catch(error=>{console.error(error);process.exit(2)})`
	probeContext, cancel := context.WithTimeout(ctx, 20*time.Second)
	defer cancel()
	command := exec.CommandContext(probeContext, "node", "-e", probe, runtime.Root, runtime.Launcher)
	if output, err := command.CombinedOutput(); err != nil {
		return fmt.Errorf("browser runtime startup check failed: %w: %s", err, strings.TrimSpace(string(output)))
	}
	return nil
}

func (runtime ReportBrowserRuntime) commandEnvironment() []string {
	environment := make([]string, 0, len(os.Environ())+2)
	for _, item := range os.Environ() {
		if strings.HasPrefix(item, "FACTORY_BROWSER_LAUNCHER=") || strings.HasPrefix(item, "FACTORY_BROWSER_RUNTIME=") {
			continue
		}
		environment = append(environment, item)
	}
	environment = append(environment, "FACTORY_BROWSER_LAUNCHER="+runtime.Launcher)
	environment = append(environment, "FACTORY_BROWSER_RUNTIME="+runtime.Root)
	return environment
}

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
