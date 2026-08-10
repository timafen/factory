package cyrillicaudit

import (
	"context"
	"database/sql"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	_ "modernc.org/sqlite"
)

func TestAuditInventoriesWithoutChangingOrDisclosingInputs(t *testing.T) {
	root := t.TempDir()
	databasePath := filepath.Join(root, "snapshot.sqlite3")
	database, err := sql.Open("sqlite", databasePath)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := database.Exec(`CREATE TABLE tasks (id TEXT PRIMARY KEY, title TEXT NOT NULL)`); err != nil {
		t.Fatal(err)
	}
	originalTask := "Исправить заголовок"
	damagedTask := questionDamage(originalTask)
	values := []struct{ id, title string }{
		{"recoverable-task", damagedTask},
		{"missing-task", "????"},
		{"conflict-task", "?? mismatch"},
		{"clean-task", originalTask},
	}
	for _, value := range values {
		if _, err := database.Exec(`INSERT INTO tasks(id, title) VALUES (?, ?)`, value.id, value.title); err != nil {
			t.Fatal(err)
		}
	}
	if err := database.Close(); err != nil {
		t.Fatal(err)
	}
	beforeDigest, err := digestFile(databasePath)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(databasePath, 0o444); err != nil {
		t.Fatal(err)
	}

	repository := filepath.Join(root, "repository")
	if err := os.Mkdir(repository, 0o755); err != nil {
		t.Fatal(err)
	}
	runGit(t, repository, "init", "-q")
	runGit(t, repository, "config", "user.name", "Audit Test")
	runGit(t, repository, "config", "user.email", "audit@example.invalid")
	if err := os.WriteFile(filepath.Join(repository, "evidence.txt"), []byte("evidence\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	runGit(t, repository, "add", "evidence.txt")
	originalSubject := "Сохранить русский коммит"
	damagedSubject := questionDamage(originalSubject)
	runGit(t, repository, "commit", "-q", "-m", damagedSubject)
	revision := strings.TrimSpace(runGit(t, repository, "rev-parse", "HEAD"))
	statusBefore := runGit(t, repository, "status", "--porcelain=v1")

	sources := Sources{
		SchemaVersion: SchemaVersion,
		Tasks: []TaskSource{
			{TaskID: "recoverable-task", SourceKind: "github_issue", SourceID: "owner/repo#7", Title: originalTask},
			{TaskID: "conflict-task", SourceKind: "reviewed_export", SourceID: "record-2", Title: "Другой текст"},
		},
		Commits: []CommitSource{{
			RepositoryID: "factory", RepositoryPath: repository, Revision: revision,
			SourceKind: "reviewed_export", SourceID: "commit-record-1", Subject: originalSubject,
		}},
	}
	report, err := Audit(context.Background(), databasePath, sources)
	if err != nil {
		t.Fatal(err)
	}
	if report.SnapshotSHA256 != beforeDigest {
		t.Fatalf("reported snapshot digest = %q, want %q", report.SnapshotSHA256, beforeDigest)
	}
	if report.Counts.DamagedTasks != 3 || report.Counts.RecoverableTasks != 1 {
		t.Fatalf("task counts = %#v", report.Counts)
	}
	if report.Counts.CommitsChecked != 1 || report.Counts.DamagedCommits != 1 || report.Counts.RecoverableCommits != 1 {
		t.Fatalf("commit counts = %#v", report.Counts)
	}
	comparisons := map[string]string{}
	for _, finding := range report.Tasks {
		comparisons[finding.TaskID] = finding.Comparison
	}
	if comparisons["recoverable-task"] != "recoverable" || comparisons["missing-task"] != "missing_source" ||
		comparisons["conflict-task"] != "conflict" {
		t.Fatalf("task comparisons = %#v", comparisons)
	}
	if len(report.Commits) != 1 || report.Commits[0].Comparison != "recoverable" || report.Commits[0].Revision != revision {
		t.Fatalf("commit findings = %#v", report.Commits)
	}

	encoded, err := json.Marshal(report)
	if err != nil {
		t.Fatal(err)
	}
	for _, secret := range []string{originalTask, damagedTask, originalSubject, damagedSubject} {
		if strings.Contains(string(encoded), secret) {
			t.Fatalf("report disclosed investigated text")
		}
	}
	afterDigest, err := digestFile(databasePath)
	if err != nil {
		t.Fatal(err)
	}
	if afterDigest != beforeDigest {
		t.Fatalf("database changed: before %s, after %s", beforeDigest, afterDigest)
	}
	if statusAfter := runGit(t, repository, "status", "--porcelain=v1"); statusAfter != statusBefore {
		t.Fatalf("git state changed: before %q, after %q", statusBefore, statusAfter)
	}
	for _, suffix := range []string{"-wal", "-shm"} {
		if _, err := os.Stat(databasePath + suffix); !os.IsNotExist(err) {
			t.Fatalf("read-only audit created %s", databasePath+suffix)
		}
	}
}

func TestReadSourcesRejectsUnverifiableInput(t *testing.T) {
	tests := []string{
		`{"schema_version":2}`,
		`{"schema_version":1,"tasks":[{"task_id":"one","source_kind":"x","source_id":"1","title":"a"},{"task_id":"one","source_kind":"x","source_id":"2","title":"b"}]}`,
		`{"schema_version":1,"commits":[{"repository_id":"repo","repository_path":".","revision":"short","source_kind":"x","source_id":"1","subject":"x"}]}`,
	}
	for _, input := range tests {
		if _, err := ReadSources(strings.NewReader(input)); err == nil {
			t.Fatalf("invalid sources accepted: %s", input)
		}
	}
}

func TestCompareDoesNotTreatExistingQuestionMarkAsEvidence(t *testing.T) {
	if comparison := compare("Что?", "Что?"); comparison != "exact" {
		t.Fatalf("exact comparison = %q", comparison)
	}
	if comparison := compare("???", "А?Б"); comparison != "conflict" {
		t.Fatalf("ambiguous comparison = %q", comparison)
	}
}

func TestGitSubjectDoesNotLazyFetchMissingPromisorObject(t *testing.T) {
	root := t.TempDir()
	origin := filepath.Join(root, "origin")
	client := filepath.Join(root, "client")
	if err := os.Mkdir(origin, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(client, 0o755); err != nil {
		t.Fatal(err)
	}
	runGit(t, origin, "init", "-q")
	runGit(t, origin, "config", "user.name", "Audit Test")
	runGit(t, origin, "config", "user.email", "audit@example.invalid")
	runGit(t, origin, "commit", "--allow-empty", "-q", "-m", "???? ??????")
	revision := strings.TrimSpace(runGit(t, origin, "rev-parse", "HEAD"))

	runGit(t, client, "init", "-q")
	runGit(t, client, "remote", "add", "origin", origin)
	runGit(t, client, "config", "remote.origin.promisor", "true")
	runGit(t, client, "config", "remote.origin.partialclonefilter", "blob:none")
	objectsPath := filepath.Join(client, ".git", "objects")
	before := countFiles(t, objectsPath)

	if _, err := gitSubject(context.Background(), client, revision); err == nil {
		t.Fatal("missing promisor commit was fetched")
	}
	if after := countFiles(t, objectsPath); after != before {
		t.Fatalf("git object store changed: before %d files, after %d", before, after)
	}
}

func TestGitSubjectIgnoresReplacementRefs(t *testing.T) {
	repository := t.TempDir()
	runGit(t, repository, "init", "-q")
	runGit(t, repository, "config", "user.name", "Audit Test")
	runGit(t, repository, "config", "user.email", "audit@example.invalid")
	damagedSubject := "???? ??????"
	runGit(t, repository, "commit", "--allow-empty", "-q", "-m", damagedSubject)
	revision := strings.TrimSpace(runGit(t, repository, "rev-parse", "HEAD"))
	runGit(t, repository, "commit", "--allow-empty", "-q", "-m", "Подменённый заголовок")
	replacement := strings.TrimSpace(runGit(t, repository, "rev-parse", "HEAD"))
	runGit(t, repository, "replace", revision, replacement)

	subject, err := gitSubject(context.Background(), repository, revision)
	if err != nil {
		t.Fatal(err)
	}
	if subject != damagedSubject {
		t.Fatalf("subject = %q, want original object subject", subject)
	}
}

func TestGitSubjectAcceptsUppercaseCommitSHA(t *testing.T) {
	repository := t.TempDir()
	runGit(t, repository, "init", "-q")
	runGit(t, repository, "config", "user.name", "Audit Test")
	runGit(t, repository, "config", "user.email", "audit@example.invalid")
	subject := "???? ??????"
	runGit(t, repository, "commit", "--allow-empty", "-q", "-m", subject)
	revision := strings.ToUpper(strings.TrimSpace(runGit(t, repository, "rev-parse", "HEAD")))

	actual, err := gitSubject(context.Background(), repository, revision)
	if err != nil {
		t.Fatal(err)
	}
	if actual != subject {
		t.Fatalf("subject = %q, want %q", actual, subject)
	}
}

func TestGitSubjectRejectsNonCommitObjects(t *testing.T) {
	repository := t.TempDir()
	runGit(t, repository, "init", "-q")
	runGit(t, repository, "config", "user.name", "Audit Test")
	runGit(t, repository, "config", "user.email", "audit@example.invalid")
	if err := os.WriteFile(filepath.Join(repository, "evidence.txt"), []byte("blob contents\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	runGit(t, repository, "add", "evidence.txt")
	runGit(t, repository, "commit", "-q", "-m", "???? ??????")

	objects := map[string]string{
		"tree": strings.TrimSpace(runGit(t, repository, "rev-parse", "HEAD^{tree}")),
		"blob": strings.TrimSpace(runGit(t, repository, "rev-parse", "HEAD:evidence.txt")),
	}
	for objectType, revision := range objects {
		t.Run(objectType, func(t *testing.T) {
			if _, err := gitSubject(context.Background(), repository, revision); err == nil {
				t.Fatalf("%s object was accepted as a commit", objectType)
			}
		})
	}
}

func questionDamage(value string) string {
	return strings.Map(func(character rune) rune {
		if character > 127 {
			return '?'
		}
		return character
	}, value)
}

func runGit(t *testing.T, directory string, arguments ...string) string {
	t.Helper()
	command := exec.Command("git", append([]string{"-C", directory}, arguments...)...)
	command.Env = append(os.Environ(), "GIT_OPTIONAL_LOCKS=0")
	output, err := command.CombinedOutput()
	if err != nil {
		t.Fatalf("git %v: %v: %s", arguments, err, output)
	}
	return string(output)
}

func countFiles(t *testing.T, root string) int {
	t.Helper()
	count := 0
	err := filepath.WalkDir(root, func(_ string, entry os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if entry.Type().IsRegular() {
			count++
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	return count
}
