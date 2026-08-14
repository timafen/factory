package main

import (
	"os"
	"strings"
	"testing"
)

func TestInstalledBrokerExecutableMatchesProductionUnit(t *testing.T) {
	const productionPath = "/opt/factory-data/bin/factory-release-broker"
	if installedBrokerExecutable != productionPath {
		t.Fatalf("restart watches %q, want production installation %q", installedBrokerExecutable, productionPath)
	}

	unit, err := os.ReadFile("../../ops/systemd/factory-release-broker.service")
	if err != nil {
		t.Fatal(err)
	}
	wantExecStart := "ExecStart=" + installedBrokerExecutable + " --state-dir /var/lib/factory/release-broker"
	if !strings.Contains(string(unit), wantExecStart+"\n") {
		t.Fatalf("production unit does not contain %q", wantExecStart)
	}
}
