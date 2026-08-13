package controlplane

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/owainlewis/factory/internal/protocol"
)

func TestAutomationStatusCombinesDurableAndAllowlistedHostRows(t *testing.T) {
	store, durable := createAutomationFixture(t, false)
	stamp := time.Now().UTC().Add(-time.Minute)
	snapshot := struct {
		Automations []protocol.AutomationStatus `json:"automations"`
		ObservedAt  *time.Time                  `json:"observed_at"`
	}{Automations: []protocol.AutomationStatus{
		{Source: "host", ID: "factory-pilot", Status: "running", DataStatus: "ok", LastActivityAt: &stamp},
		{Source: "host", ID: "not-allowlisted", Status: "running", DataStatus: "ok", LastActivityAt: &stamp},
	}, ObservedAt: &stamp}
	body, _ := json.Marshal(snapshot)
	path := filepath.Join(t.TempDir(), "automation-status.json")
	if err := os.WriteFile(path, body, 0o600); err != nil {
		t.Fatal(err)
	}
	items, err := store.AutomationStatuses(context.Background(), path)
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 5 {
		t.Fatalf("got %d rows, want durable plus four host rows", len(items))
	}
	seen := map[string]protocol.AutomationStatus{}
	for _, item := range items {
		seen[item.ID] = item
	}
	if seen[durable.Automation.ID].Category != "automation" {
		t.Fatalf("durable Automation missing: %#v", seen)
	}
	if seen["factory-pilot"].Status != "running" {
		t.Fatalf("pilot status = %#v", seen["factory-pilot"])
	}
	if _, ok := seen["not-allowlisted"]; ok {
		t.Fatal("non-allowlisted unit leaked")
	}
	for _, id := range []string{"factory-release-broker", "factory-intake", "factory-janitor"} {
		if seen[id].DataStatus != "no_data" || seen[id].Status != "unknown" {
			t.Fatalf("%s must remain visible as no_data: %#v", id, seen[id])
		}
	}
}

func TestAutomationStatusExpiredSnapshotKeepsHostRowsAsNoData(t *testing.T) {
	store := newTestStore(t)
	stamp := time.Now().UTC().Add(-automationStatusSnapshotTTL - time.Second)
	body, _ := json.Marshal(struct {
		Automations []protocol.AutomationStatus `json:"automations"`
		ObservedAt  *time.Time                  `json:"observed_at"`
	}{Automations: []protocol.AutomationStatus{{Source: "host", ID: "factory-pilot", Status: "active", DataStatus: "ok", LastActivityAt: &stamp}}, ObservedAt: &stamp})
	path := filepath.Join(t.TempDir(), "automation-status.json")
	if err := os.WriteFile(path, body, 0o600); err != nil {
		t.Fatal(err)
	}
	items, err := store.AutomationStatuses(context.Background(), path)
	if err != nil {
		t.Fatal(err)
	}
	for _, item := range items {
		if item.Source == "host" && (item.DataStatus != "no_data" || item.Status != "unknown" || item.LastActivityAt != nil) {
			t.Fatalf("expired snapshot must not look live: %#v", item)
		}
	}
}

func TestAutomationStatusFutureSnapshotKeepsHostRowsAsNoData(t *testing.T) {
	store := newTestStore(t)
	stamp := time.Now().UTC().Add(time.Second)
	body, _ := json.Marshal(struct {
		Automations []protocol.AutomationStatus `json:"automations"`
		ObservedAt  *time.Time                  `json:"observed_at"`
	}{Automations: []protocol.AutomationStatus{{Source: "host", ID: "factory-pilot", Status: "active", DataStatus: "ok", LastActivityAt: &stamp}}, ObservedAt: &stamp})
	path := filepath.Join(t.TempDir(), "automation-status.json")
	if err := os.WriteFile(path, body, 0o600); err != nil {
		t.Fatal(err)
	}
	items, err := store.AutomationStatuses(context.Background(), path)
	if err != nil {
		t.Fatal(err)
	}
	for _, item := range items {
		if item.Source == "host" && (item.DataStatus != "no_data" || item.Status != "unknown" || item.LastActivityAt != nil) {
			t.Fatalf("future snapshot must not look live: %#v", item)
		}
	}
}

func TestAutomationStatusPathUsesConfiguredDataHome(t *testing.T) {
	home := t.TempDir()
	t.Setenv("FACTORY_DATA_HOME", home)
	if got, want := automationStatusPath(), filepath.Join(home, "pilot", "automation-status.json"); got != want {
		t.Fatalf("automationStatusPath() = %q, want %q", got, want)
	}
}

func TestAutomationStatusUnavailableSnapshotKeepsHostRows(t *testing.T) {
	store := newTestStore(t)
	items, err := store.AutomationStatuses(context.Background(), filepath.Join(t.TempDir(), "missing.json"))
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != len(hostAutomationInventory) {
		t.Fatalf("got %d host rows", len(items))
	}
	for _, item := range items {
		if item.DataStatus != "no_data" || item.LastActivityAt != nil {
			t.Fatalf("bad fallback: %#v", item)
		}
	}
}
