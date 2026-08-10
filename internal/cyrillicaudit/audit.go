// Package cyrillicaudit inventories question-mark damage without changing its inputs.
package cyrillicaudit

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strings"

	_ "modernc.org/sqlite"
)

const SchemaVersion = 1

var fullCommit = regexp.MustCompile(`^[0-9a-fA-F]{40}$`)

type Sources struct {
	SchemaVersion int            `json:"schema_version"`
	Tasks         []TaskSource   `json:"tasks"`
	Commits       []CommitSource `json:"commits"`
}

type TaskSource struct {
	TaskID     string `json:"task_id"`
	SourceKind string `json:"source_kind"`
	SourceID   string `json:"source_id"`
	Title      string `json:"title"`
}

type CommitSource struct {
	RepositoryID   string `json:"repository_id"`
	RepositoryPath string `json:"repository_path"`
	Revision       string `json:"revision"`
	SourceKind     string `json:"source_kind"`
	SourceID       string `json:"source_id"`
	Subject        string `json:"subject"`
}

type Report struct {
	SchemaVersion  int             `json:"schema_version"`
	SnapshotSHA256 string          `json:"snapshot_sha256"`
	Counts         Counts          `json:"counts"`
	Tasks          []TaskFinding   `json:"tasks"`
	Commits        []CommitFinding `json:"commits"`
}

type Counts struct {
	DamagedTasks       int `json:"damaged_tasks"`
	RecoverableTasks   int `json:"recoverable_tasks"`
	CommitsChecked     int `json:"commits_checked"`
	DamagedCommits     int `json:"damaged_commits"`
	RecoverableCommits int `json:"recoverable_commits"`
}

type TaskFinding struct {
	TaskID        string `json:"task_id"`
	QuestionMarks int    `json:"question_marks"`
	SourceKind    string `json:"source_kind,omitempty"`
	SourceID      string `json:"source_id,omitempty"`
	Comparison    string `json:"comparison"`
}

type CommitFinding struct {
	RepositoryID  string `json:"repository_id"`
	Revision      string `json:"revision"`
	QuestionMarks int    `json:"question_marks"`
	SourceKind    string `json:"source_kind"`
	SourceID      string `json:"source_id"`
	Comparison    string `json:"comparison"`
}

func ReadSources(reader io.Reader) (Sources, error) {
	var sources Sources
	decoder := json.NewDecoder(reader)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&sources); err != nil {
		return sources, fmt.Errorf("decode sources: %w", err)
	}
	if err := ensureJSONEnd(decoder); err != nil {
		return sources, err
	}
	if sources.SchemaVersion != SchemaVersion {
		return sources, fmt.Errorf("unsupported sources schema_version %d", sources.SchemaVersion)
	}
	return sources, validateSources(sources)
}

func ensureJSONEnd(decoder *json.Decoder) error {
	var extra any
	if err := decoder.Decode(&extra); errors.Is(err, io.EOF) {
		return nil
	} else if err != nil {
		return fmt.Errorf("decode sources: %w", err)
	}
	return errors.New("decode sources: multiple JSON values")
}

func validateSources(sources Sources) error {
	seenTasks := make(map[string]bool, len(sources.Tasks))
	for _, source := range sources.Tasks {
		if strings.TrimSpace(source.TaskID) == "" || strings.TrimSpace(source.SourceKind) == "" ||
			strings.TrimSpace(source.SourceID) == "" {
			return errors.New("task sources require task_id, source_kind, and source_id")
		}
		if seenTasks[source.TaskID] {
			return fmt.Errorf("duplicate task source for task_id %q", source.TaskID)
		}
		seenTasks[source.TaskID] = true
	}
	seenCommits := make(map[string]bool, len(sources.Commits))
	for _, source := range sources.Commits {
		key := source.RepositoryID + "\x00" + strings.ToLower(source.Revision)
		if strings.TrimSpace(source.RepositoryID) == "" || strings.TrimSpace(source.RepositoryPath) == "" ||
			strings.TrimSpace(source.SourceKind) == "" || strings.TrimSpace(source.SourceID) == "" ||
			!fullCommit.MatchString(source.Revision) {
			return errors.New("commit sources require repository_id, repository_path, source_kind, source_id, and a full commit SHA")
		}
		if seenCommits[key] {
			return errors.New("duplicate commit source")
		}
		seenCommits[key] = true
	}
	return nil
}

func Audit(ctx context.Context, databasePath string, sources Sources) (Report, error) {
	report := Report{SchemaVersion: SchemaVersion, Tasks: []TaskFinding{}, Commits: []CommitFinding{}}
	if sources.SchemaVersion != SchemaVersion {
		return report, fmt.Errorf("unsupported sources schema_version %d", sources.SchemaVersion)
	}
	if err := validateSources(sources); err != nil {
		return report, err
	}
	digest, err := digestFile(databasePath)
	if err != nil {
		return report, fmt.Errorf("digest database snapshot: %w", err)
	}
	report.SnapshotSHA256 = digest

	tasks, err := damagedTasks(ctx, databasePath)
	if err != nil {
		return report, err
	}
	taskSources := make(map[string]TaskSource, len(sources.Tasks))
	for _, source := range sources.Tasks {
		taskSources[source.TaskID] = source
	}
	for _, task := range tasks {
		finding := TaskFinding{TaskID: task.id, QuestionMarks: strings.Count(task.title, "?"), Comparison: "missing_source"}
		if source, ok := taskSources[task.id]; ok {
			finding.SourceKind, finding.SourceID = source.SourceKind, source.SourceID
			finding.Comparison = compare(task.title, source.Title)
		}
		report.Tasks = append(report.Tasks, finding)
		if finding.Comparison == "recoverable" {
			report.Counts.RecoverableTasks++
		}
	}
	report.Counts.DamagedTasks = len(report.Tasks)

	for _, source := range sources.Commits {
		report.Counts.CommitsChecked++
		actual, err := gitSubject(ctx, source.RepositoryPath, source.Revision)
		if err != nil {
			return report, fmt.Errorf("inspect labelled commit for repository %q: %w", source.RepositoryID, err)
		}
		if !strings.Contains(actual, "?") {
			continue
		}
		finding := CommitFinding{
			RepositoryID: source.RepositoryID, Revision: strings.ToLower(source.Revision),
			QuestionMarks: strings.Count(actual, "?"), SourceKind: source.SourceKind,
			SourceID: source.SourceID, Comparison: compare(actual, source.Subject),
		}
		report.Commits = append(report.Commits, finding)
		if finding.Comparison == "recoverable" {
			report.Counts.RecoverableCommits++
		}
	}
	report.Counts.DamagedCommits = len(report.Commits)
	sort.Slice(report.Commits, func(i, j int) bool {
		if report.Commits[i].RepositoryID == report.Commits[j].RepositoryID {
			return report.Commits[i].Revision < report.Commits[j].Revision
		}
		return report.Commits[i].RepositoryID < report.Commits[j].RepositoryID
	})
	return report, nil
}

type taskText struct{ id, title string }

func damagedTasks(ctx context.Context, path string) ([]taskText, error) {
	absolute, err := filepath.Abs(path)
	if err != nil {
		return nil, fmt.Errorf("resolve database snapshot: %w", err)
	}
	u := &url.URL{Scheme: "file", Path: absolute, RawQuery: "mode=ro&immutable=1"}
	database, err := sql.Open("sqlite", u.String())
	if err != nil {
		return nil, fmt.Errorf("open immutable database snapshot: %w", err)
	}
	defer database.Close()
	database.SetMaxOpenConns(1)
	rows, err := database.QueryContext(ctx, `SELECT id, title FROM tasks WHERE instr(title, '?') > 0 ORDER BY id`)
	if err != nil {
		return nil, fmt.Errorf("inventory task titles: %w", err)
	}
	defer rows.Close()
	var result []taskText
	for rows.Next() {
		var task taskText
		if err := rows.Scan(&task.id, &task.title); err != nil {
			return nil, fmt.Errorf("read task inventory: %w", err)
		}
		result = append(result, task)
	}
	return result, rows.Err()
}

func compare(damaged, original string) string {
	if damaged == original {
		return "exact"
	}
	damagedRunes, originalRunes := []rune(damaged), []rune(original)
	if len(damagedRunes) != len(originalRunes) {
		return "conflict"
	}
	for index := range damagedRunes {
		if damagedRunes[index] == '?' && originalRunes[index] == '?' {
			return "conflict"
		}
		if damagedRunes[index] != '?' && damagedRunes[index] != originalRunes[index] {
			return "conflict"
		}
	}
	return "recoverable"
}

func gitSubject(ctx context.Context, repositoryPath, revision string) (string, error) {
	objectType, err := gitOutput(ctx, repositoryPath, "cat-file", "-t", revision)
	if err != nil {
		return "", errors.New("git cat-file failed")
	}
	if strings.TrimSuffix(string(objectType), "\n") != "commit" {
		return "", errors.New("revision is not a commit")
	}

	output, err := gitOutput(ctx, repositoryPath, "show", "--no-patch", "--format=%H%x00%s", revision)
	if err != nil {
		return "", errors.New("git show failed")
	}
	identity, subject, found := strings.Cut(strings.TrimSuffix(string(output), "\n"), "\x00")
	if !found || identity != revision {
		return "", errors.New("git show returned a different commit")
	}
	return subject, nil
}

func gitOutput(ctx context.Context, repositoryPath string, arguments ...string) ([]byte, error) {
	command := exec.CommandContext(ctx, "git", append([]string{"-C", repositoryPath}, arguments...)...)
	command.Env = append(os.Environ(),
		"GIT_NO_LAZY_FETCH=1",
		"GIT_NO_REPLACE_OBJECTS=1",
		"GIT_OPTIONAL_LOCKS=0",
		"LANG=C.UTF-8",
		"LC_ALL=C.UTF-8",
	)
	return command.Output()
}

func digestFile(path string) (string, error) {
	file, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer file.Close()
	hash := sha256.New()
	if _, err := io.Copy(hash, file); err != nil {
		return "", err
	}
	return hex.EncodeToString(hash.Sum(nil)), nil
}
