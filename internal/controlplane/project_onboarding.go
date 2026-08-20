package controlplane

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/owainlewis/factory/internal/protocol"
)

const (
	projectOnboardingSchemaVersion = "project-onboarding.v1"
	projectOnboardingMaxBytes      = 1 << 20
)

type ProjectOnboardingCommand struct {
	Argv []string `json:"argv"`
}

type ProjectOnboardingCommands struct {
	WorkingDirectory string                   `json:"working_directory"`
	Install          ProjectOnboardingCommand `json:"install"`
	Test             ProjectOnboardingCommand `json:"test"`
	Build            ProjectOnboardingCommand `json:"build"`
}

type ProjectOnboardingRuntime struct {
	OS               string `json:"os"`
	Architecture     string `json:"architecture"`
	Toolchain        string `json:"toolchain"`
	ToolchainVersion string `json:"toolchain_version"`
}

type ProjectOnboardingEnvironment struct {
	Network string `json:"network"`
	Secrets string `json:"secrets"`
}

type ProjectOnboardingPolicy struct {
	Write       string `json:"write"`
	PullRequest string `json:"pull_request"`
	Release     string `json:"release"`
}

// ProjectOnboardingInput is the owner-configured, inert portion of a project card.
// It is persisted for a future doctor/trial implementation but never executed here.
type ProjectOnboardingInput struct {
	ProjectID                string                       `json:"project_id"`
	Name                     string                       `json:"name"`
	DefaultBranch            string                       `json:"default_branch"`
	AllowedPaths             []string                     `json:"allowed_paths"`
	RequiredInstructionFiles []string                     `json:"required_instruction_files"`
	Commands                 ProjectOnboardingCommands    `json:"commands"`
	TimeoutSeconds           int                          `json:"timeout_seconds"`
	Runtime                  ProjectOnboardingRuntime     `json:"runtime"`
	Environment              ProjectOnboardingEnvironment `json:"environment"`
	Policy                   ProjectOnboardingPolicy      `json:"policy"`
}

// ProjectOnboardingCard keeps execution/readiness fields server-owned and unset.
// Enabled is always false in this persistence-only slice.
type ProjectOnboardingCard struct {
	SchemaVersion  string `json:"schema_version"`
	RepositoryID   string `json:"repository_id"`
	RemoteIdentity string `json:"remote_identity"`
	Enabled        bool   `json:"enabled"`
	ProjectOnboardingInput
	DiscoveredInstructionFiles []string  `json:"discovered_instruction_files,omitempty"`
	ReadinessState             string    `json:"readiness_state,omitempty"`
	ReadinessReason            string    `json:"readiness_reason,omitempty"`
	LastPreflightReceipt       any       `json:"last_preflight_receipt,omitempty"`
	LastTrialReceipt           any       `json:"last_trial_receipt,omitempty"`
	UpdatedAt                  time.Time `json:"updated_at"`
}

type ProjectOnboardingService struct {
	root         string
	repositories *Store
	now          func() time.Time
	mu           sync.Mutex
}

func NewProjectOnboardingService(root string, repositories *Store) *ProjectOnboardingService {
	root = strings.TrimSpace(root)
	if root == "" {
		root = "/opt/factory-data/project-onboarding"
	}
	return &ProjectOnboardingService{
		root:         root,
		repositories: repositories,
		now:          func() time.Time { return time.Now().UTC() },
	}
}

func (s *ProjectOnboardingService) Get(ctx context.Context, repositoryID string) (ProjectOnboardingCard, error) {
	repository, err := s.repository(ctx, repositoryID)
	if err != nil {
		return ProjectOnboardingCard{}, err
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	card, err := s.read(repository.ID)
	if err != nil {
		return ProjectOnboardingCard{}, err
	}
	if card.RemoteIdentity != repository.RemoteIdentity {
		return ProjectOnboardingCard{}, conflict("onboarding_repository_mismatch", "saved onboarding card does not match the managed repository")
	}
	return card, nil
}

func (s *ProjectOnboardingService) Put(ctx context.Context, repositoryID string, input ProjectOnboardingInput) (ProjectOnboardingCard, error) {
	repository, err := s.repository(ctx, repositoryID)
	if err != nil {
		return ProjectOnboardingCard{}, err
	}
	if repository.Enabled {
		return ProjectOnboardingCard{}, conflict("onboarding_routing_enabled", "disable repository routing before saving an onboarding card")
	}
	if err := validateProjectOnboardingInput(input); err != nil {
		return ProjectOnboardingCard{}, err
	}
	card := ProjectOnboardingCard{
		SchemaVersion:          projectOnboardingSchemaVersion,
		RepositoryID:           repository.ID,
		RemoteIdentity:         repository.RemoteIdentity,
		Enabled:                false,
		ProjectOnboardingInput: input,
		UpdatedAt:              s.now(),
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if err := s.write(card); err != nil {
		return ProjectOnboardingCard{}, err
	}
	return card, nil
}

func (s *ProjectOnboardingService) repository(ctx context.Context, repositoryID string) (protocol.ManagedRepository, error) {
	if s == nil || s.repositories == nil {
		return protocol.ManagedRepository{}, unavailable(errors.New("project onboarding is unavailable"))
	}
	if !validUUID(strings.TrimSpace(repositoryID)) {
		return protocol.ManagedRepository{}, invalid("invalid_repository", "repository_id must be a UUID")
	}
	return s.repositories.ManagedRepository(ctx, repositoryID)
}

func (s *ProjectOnboardingService) cardPath(repositoryID string) string {
	return filepath.Join(s.root, "cards", repositoryID+".json")
}

func (s *ProjectOnboardingService) read(repositoryID string) (ProjectOnboardingCard, error) {
	path := s.cardPath(repositoryID)
	info, err := os.Lstat(path)
	if errors.Is(err, fs.ErrNotExist) {
		return ProjectOnboardingCard{}, ErrNotFound
	}
	if err != nil {
		return ProjectOnboardingCard{}, unavailable(err)
	}
	if !info.Mode().IsRegular() || info.Mode()&os.ModeSymlink != 0 || info.Size() > projectOnboardingMaxBytes {
		return ProjectOnboardingCard{}, unavailable(errors.New("onboarding card must be a bounded regular file"))
	}
	body, err := os.ReadFile(path)
	if err != nil {
		return ProjectOnboardingCard{}, unavailable(err)
	}
	var card ProjectOnboardingCard
	decoder := json.NewDecoder(bytes.NewReader(body))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&card); err != nil {
		return ProjectOnboardingCard{}, unavailable(err)
	}
	if card.SchemaVersion != projectOnboardingSchemaVersion || card.RepositoryID != repositoryID || card.Enabled ||
		len(card.DiscoveredInstructionFiles) != 0 || card.ReadinessState != "" || card.ReadinessReason != "" ||
		card.LastPreflightReceipt != nil || card.LastTrialReceipt != nil {
		return ProjectOnboardingCard{}, unavailable(errors.New("invalid or active onboarding card"))
	}
	return card, nil
}

func (s *ProjectOnboardingService) write(card ProjectOnboardingCard) error {
	directory := filepath.Dir(s.cardPath(card.RepositoryID))
	if err := os.MkdirAll(directory, 0o700); err != nil {
		return unavailable(err)
	}
	if info, err := os.Lstat(directory); err != nil || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
		if err == nil {
			err = errors.New("onboarding card directory must not be a symlink")
		}
		return unavailable(err)
	}
	body, err := json.MarshalIndent(card, "", "  ")
	if err != nil {
		return unavailable(err)
	}
	body = append(body, '\n')
	if len(body) > projectOnboardingMaxBytes {
		return invalid("invalid_onboarding_card", "onboarding card is too large")
	}
	temporary, err := os.CreateTemp(directory, ".card-*.tmp")
	if err != nil {
		return unavailable(err)
	}
	temporaryPath := temporary.Name()
	defer os.Remove(temporaryPath)
	if err := temporary.Chmod(0o600); err != nil {
		temporary.Close()
		return unavailable(err)
	}
	if _, err := temporary.Write(body); err != nil {
		temporary.Close()
		return unavailable(err)
	}
	if err := temporary.Sync(); err != nil {
		temporary.Close()
		return unavailable(err)
	}
	if err := temporary.Close(); err != nil {
		return unavailable(err)
	}
	if err := os.Rename(temporaryPath, s.cardPath(card.RepositoryID)); err != nil {
		return unavailable(err)
	}
	return nil
}

func validateProjectOnboardingInput(input ProjectOnboardingInput) error {
	if !validSlug(input.ProjectID) {
		return invalid("invalid_onboarding_card", "project_id must use lowercase letters, numbers, and single hyphens")
	}
	if name := strings.TrimSpace(input.Name); name == "" || len(name) > 120 {
		return invalid("invalid_onboarding_card", "name is required and must not exceed 120 characters")
	}
	if input.DefaultBranch == "" || len(input.DefaultBranch) > 255 || strings.ContainsAny(input.DefaultBranch, " ~^:?*[\\") || strings.Contains(input.DefaultBranch, "..") {
		return invalid("invalid_onboarding_card", "default_branch is invalid")
	}
	if input.TimeoutSeconds < 1 || input.TimeoutSeconds > 1800 {
		return invalid("invalid_onboarding_card", "timeout_seconds must be between 1 and 1800")
	}
	if input.Environment.Network != "NONE" || input.Environment.Secrets != "NONE" {
		return invalid("unsafe_onboarding_card", "network and secrets must both be NONE")
	}
	if strings.TrimSpace(input.Runtime.OS) == "" || strings.TrimSpace(input.Runtime.Architecture) == "" ||
		strings.TrimSpace(input.Runtime.Toolchain) == "" || strings.TrimSpace(input.Runtime.ToolchainVersion) == "" {
		return invalid("invalid_onboarding_card", "runtime fields are required")
	}
	if input.Policy.Release != "DISABLED" || (input.Policy.Write != "NONE" && input.Policy.Write != "DOCS_ONLY") || (input.Policy.PullRequest != "DISABLED" && input.Policy.PullRequest != "DRAFT_ONLY") {
		return invalid("unsafe_onboarding_card", "write, pull request, or release policy is outside the onboarding safety envelope")
	}
	if len(input.AllowedPaths) > 64 || len(input.RequiredInstructionFiles) > 64 {
		return invalid("invalid_onboarding_card", "too many paths or instruction files")
	}
	for _, path := range append(append([]string{}, input.AllowedPaths...), input.RequiredInstructionFiles...) {
		if !safeRelativePath(path) {
			return invalid("invalid_onboarding_card", "allowed paths and instruction files must be safe relative paths")
		}
	}
	if input.Policy.Write == "DOCS_ONLY" && len(input.AllowedPaths) == 0 {
		return invalid("invalid_onboarding_card", "DOCS_ONLY requires at least one allowed path")
	}
	for _, command := range []ProjectOnboardingCommand{input.Commands.Install, input.Commands.Test, input.Commands.Build} {
		if err := validateProjectOnboardingCommand(command); err != nil {
			return err
		}
	}
	if input.Commands.WorkingDirectory != "" && !safeRelativePath(input.Commands.WorkingDirectory) {
		return invalid("invalid_onboarding_card", "working_directory must be a safe relative path")
	}
	return nil
}

func validateProjectOnboardingCommand(command ProjectOnboardingCommand) error {
	if len(command.Argv) == 0 {
		return nil
	}
	if len(command.Argv) > 64 {
		return invalid("invalid_onboarding_card", "command has too many arguments")
	}
	allowed := map[string]bool{"git": true, "go": true, "npm": true, "php": true, "composer": true, "python3": true}
	if !allowed[command.Argv[0]] {
		return invalid("unsafe_onboarding_command", "command executable is not allowed")
	}
	for _, argument := range command.Argv {
		if argument == "" || len(argument) > 4096 || strings.ContainsAny(argument, "\x00\r\n") || strings.Contains(argument, "&&") || strings.Contains(argument, "||") || strings.ContainsAny(argument, ";<>`") || strings.Contains(argument, "$(") {
			return invalid("unsafe_onboarding_command", "command arguments must not contain shell syntax")
		}
	}
	return nil
}

func validSlug(value string) bool {
	if len(value) < 1 || len(value) > 80 || value[0] == '-' || value[len(value)-1] == '-' || strings.Contains(value, "--") {
		return false
	}
	for _, character := range value {
		if (character < 'a' || character > 'z') && (character < '0' || character > '9') && character != '-' {
			return false
		}
	}
	return true
}

func safeRelativePath(value string) bool {
	if value == "" || filepath.IsAbs(value) || strings.Contains(value, "\\") {
		return false
	}
	clean := filepath.ToSlash(filepath.Clean(value))
	return clean != "." && clean != ".." && !strings.HasPrefix(clean, "../") && clean == value
}
