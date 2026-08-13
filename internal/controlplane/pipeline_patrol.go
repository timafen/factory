package controlplane

import (
	"context"
	"database/sql"
	"strings"

	"github.com/owainlewis/factory/internal/protocol"
)

// PipelinePatrolInstruction is deliberately kept in the Automation context.
// Schedule occurrences snapshot that context, so a restarted control plane
// cannot lose the patrol's instructions or replace old run evidence.
const PipelinePatrolInstruction = `Factory pipeline patrol. Inspect only canonical [auto] [N/M Stage] pipeline tasks. Do not touch an owner-paused pipeline or a final stage. If a succeeded stage has no live successor, wait 450 seconds before continuing it, preserve its repository, workflow revision and worker route, and make at most two continuation attempts. Escalate the stalled work once after those attempts. Record the outcome and diagnostic in this Automation run.`

const legacyPipelinePatrolInstruction = `Factory pipeline patrol. Inspect only canonical [auto] [N/M Stage] pipeline tasks. Do not touch an owner-paused pipeline or a final stage. If a succeeded stage has no live successor, wait 600 seconds before continuing it, preserve its repository, workflow revision and worker route, and make at most two continuation attempts. Escalate the stalled work once after those attempts. Record the outcome and diagnostic in this Automation run.`

const PipelinePatrolModelID = "gpt-5.6-terra"

// ProvisionPipelinePatrol turns an already configured schedule Automation into
// the single durable runner for the pipeline patrol.  The caller supplies the
// existing Automation ID: cron and timezone are never invented by Factory.
func (s *Store) ProvisionPipelinePatrol(ctx context.Context, automationID string) (protocol.AutomationDetail, error) {
	automationID = strings.TrimSpace(automationID)
	if automationID == "" {
		return protocol.AutomationDetail{}, invalid("pipeline_patrol_automation_required", "an existing schedule Automation is required for the pipeline patrol")
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return protocol.AutomationDetail{}, unavailable(err)
	}
	defer tx.Rollback()
	snapshot, err := loadScheduleSnapshot(ctx, tx, automationID)
	if err != nil {
		return protocol.AutomationDetail{}, err
	}
	if !snapshot.workflowEnabled || !snapshot.repositoryEnabled {
		message := "Pipeline patrol is blocked: enable its Workflow and repository before provisioning."
		if _, err := tx.ExecContext(ctx, `
			UPDATE automations SET health_status = 'blocked', health_code = 'pipeline_patrol_dependencies_disabled',
			       health_message = ?, updated_at = ? WHERE id = ?
		`, message, s.now().UnixMilli(), automationID); err != nil {
			return protocol.AutomationDetail{}, unavailable(err)
		}
		if err := tx.Commit(); err != nil {
			return protocol.AutomationDetail{}, unavailable(err)
		}
		return s.Automation(ctx, automationID)
	}

	contextValue := snapshot.context
	instructionChanged := false
	if strings.Contains(contextValue, legacyPipelinePatrolInstruction) {
		contextValue = strings.ReplaceAll(contextValue, legacyPipelinePatrolInstruction, PipelinePatrolInstruction)
		instructionChanged = true
	}
	addingInstruction := !strings.Contains(contextValue, PipelinePatrolInstruction)
	if addingInstruction {
		if strings.TrimSpace(contextValue) != "" {
			contextValue += "\n\n"
		}
		contextValue += PipelinePatrolInstruction
		instructionChanged = true
	}
	if len([]byte(contextValue)) > protocol.MaxAutomationContextBytes {
		return protocol.AutomationDetail{}, invalid("invalid_automation_context", "context is limited to 8 KiB")
	}
	now := s.now()
	nextDue := snapshot.nextDueAt
	if !nextDue.Valid {
		schedule, _, _, parseErr := parseCronSchedule(snapshot.cron, snapshot.timezone)
		if parseErr != nil {
			return protocol.AutomationDetail{}, unavailable(parseErr)
		}
		next, nextErr := schedule.Next(now)
		if nextErr != nil {
			return protocol.AutomationDetail{}, unavailable(nextErr)
		}
		nextDue = sql.NullInt64{Int64: next.UnixMilli(), Valid: true}
	}
	versionIncrement := 0
	if instructionChanged || snapshot.modelID != PipelinePatrolModelID {
		versionIncrement = 1
	}
	result, err := tx.ExecContext(ctx, `
		UPDATE automations
		SET context = ?, model_id = ?, version = version + ?, enabled = 1, health_status = 'healthy', health_code = '',
		    health_message = 'Pipeline patrol provisioned from the existing schedule.', updated_at = ?
		WHERE id = ? AND version = ?
	`, contextValue, PipelinePatrolModelID, versionIncrement, now.UnixMilli(), automationID, snapshot.automationVersion)
	if err != nil {
		return protocol.AutomationDetail{}, unavailable(err)
	}
	changed, err := result.RowsAffected()
	if err != nil {
		return protocol.AutomationDetail{}, unavailable(err)
	}
	if changed != 1 {
		return protocol.AutomationDetail{}, conflict("automation_version_conflict", "the Automation changed while the pipeline patrol was being provisioned")
	}
	if _, err := tx.ExecContext(ctx, `
		UPDATE automation_schedule_triggers SET next_due_at = ? WHERE automation_id = ? AND next_due_at IS NULL
	`, nextDue.Int64, automationID); err != nil {
		return protocol.AutomationDetail{}, unavailable(err)
	}
	if err := tx.Commit(); err != nil {
		return protocol.AutomationDetail{}, unavailable(err)
	}
	return s.Automation(ctx, automationID)
}
