package controlplane

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/owainlewis/factory/internal/protocol"
)

const automationStatusSnapshotTTL = 5 * time.Minute

var hostAutomationInventory = []protocol.AutomationStatus{
	{Source: "host", ID: "factory-pilot", Category: "pilot", Title: "Factory pilot", Purpose: "Управляет циклом Фабрики"},
	{Source: "host", ID: "factory-release-broker", Category: "release_broker", Title: "Release broker", Purpose: "Координирует выкладку"},
	{Source: "host", ID: "factory-intake", Category: "release", Title: "Factory intake", Purpose: "Принимает и выкладывает изменения"},
	{Source: "host", ID: "factory-janitor", Category: "janitor", Title: "Factory janitor", Purpose: "Очищает временные ресурсы"},
}

func automationStatusPath() string {
	home := os.Getenv("FACTORY_DATA_HOME")
	if home == "" {
		home = "/opt/factory-data"
	}
	return filepath.Join(home, "pilot", "automation-status.json")
}

func (s *Store) AutomationStatuses(ctx context.Context, snapshotPath string) ([]protocol.AutomationStatus, error) {
	var automations []protocol.Automation
	var cursor *protocol.AutomationCursor
	for {
		page, err := s.AutomationsPage(ctx, protocol.MaxAutomationPageSize, cursor)
		if err != nil {
			return nil, err
		}
		automations = append(automations, page.Automations...)
		if page.NextCursor == nil {
			break
		}
		cursor = page.NextCursor
	}
	items := make([]protocol.AutomationStatus, 0, len(automations)+len(hostAutomationInventory))
	for _, automation := range automations {
		last := automation.LastCheckedAt
		if automation.LatestRun != nil && (last == nil || automation.LatestRun.UpdatedAt.After(*last)) {
			value := automation.LatestRun.UpdatedAt
			last = &value
		}
		dataStatus := "ok"
		if last == nil {
			dataStatus = "no_data"
		}
		items = append(items, protocol.AutomationStatus{Source: "control_plane", ID: automation.ID, Category: "automation", Title: automation.Title, Purpose: automation.WorkflowTitle, Status: automation.Health.Status, DataStatus: dataStatus, LastActivityAt: last})
	}
	host := map[string]protocol.AutomationStatus{}
	body, readErr := os.ReadFile(snapshotPath)
	var snapshot struct {
		Automations []protocol.AutomationStatus `json:"automations"`
		ObservedAt  *time.Time                  `json:"observed_at"`
	}
	if readErr == nil {
		readErr = json.Unmarshal(body, &snapshot)
	}
	if readErr == nil && snapshot.ObservedAt != nil && time.Since(*snapshot.ObservedAt) <= automationStatusSnapshotTTL {
		for _, item := range snapshot.Automations {
			if item.Source == "host" {
				host[item.ID] = item
			}
		}
	}
	for _, base := range hostAutomationInventory {
		item, ok := host[base.ID]
		if !ok {
			item = base
			item.Status = "unknown"
			item.DataStatus = "no_data"
			item.Diagnostic = "Источник статуса недоступен"
		}
		item.Source, item.ID, item.Category, item.Title, item.Purpose = base.Source, base.ID, base.Category, base.Title, base.Purpose
		if item.DataStatus != "ok" || item.LastActivityAt == nil {
			item.DataStatus = "no_data"
			item.Status = "unknown"
			item.LastActivityAt = nil
		}
		item.Diagnostic = strings.TrimSpace(item.Diagnostic)
		if len(item.Diagnostic) > 200 {
			item.Diagnostic = item.Diagnostic[:200]
		}
		items = append(items, item)
	}
	sort.Slice(items, func(i, j int) bool {
		if items[i].Category == items[j].Category {
			return items[i].ID < items[j].ID
		}
		return items[i].Category < items[j].Category
	})
	return items, nil
}
