package controlplane

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"net/http"
	"os/exec"
	"regexp"
	"strings"
	"sync"
	"time"
)

// Knowledge cards live in each repository under knowledge/cards/*.md and are
// the per-feature brief the pipeline reads and updates. These endpoints give
// the UI a read-only window onto them, straight from GitHub via the already
// authenticated gh CLI. Git remains the single source of truth; the UI never
// writes cards.

const cardsDir = "knowledge/cards"

type cardSummary struct {
	RepositoryID       string `json:"repository_id"`
	RepositoryIdentity string `json:"repository_identity"`
	Path               string `json:"path"`
	Name               string `json:"name"`
	Size               int64  `json:"size"`
	Status             string `json:"status,omitempty"`
	NextAction         string `json:"next_action,omitempty"`
	GitHubURL          string `json:"github_url"`
}

type cardsCacheEntry struct {
	fetched time.Time
	cards   []cardSummary
}

var (
	cardsCacheMu sync.Mutex
	cardsCache   = map[string]cardsCacheEntry{}
)

const cardsCacheTTL = 3 * time.Minute

func ghRepoPath(remoteIdentity string) (string, bool) {
	rest, ok := strings.CutPrefix(strings.ToLower(remoteIdentity), "github.com/")
	if !ok {
		return "", false
	}
	parts := strings.Split(rest, "/")
	if len(parts) != 2 || parts[0] == "" || parts[1] == "" {
		return "", false
	}
	return parts[0] + "/" + parts[1], true
}

func runGH(ctx context.Context, args ...string) ([]byte, error) {
	ctx, cancel := context.WithTimeout(ctx, 25*time.Second)
	defer cancel()
	command := exec.CommandContext(ctx, "gh", args...)
	return command.Output()
}

var (
	statusPattern = regexp.MustCompile(`(?im)^\s*-?\s*\**Status\**\s*[:：]\s*(.+)$`)
	nextPattern   = regexp.MustCompile(`(?im)^\s*-?\s*\**(?:One exact next action|Next action|Next decision/action|Next)\**\s*[:：]\s*(.+)$`)
)

func firstMatch(pattern *regexp.Regexp, content string) string {
	match := pattern.FindStringSubmatch(content)
	if match == nil {
		return ""
	}
	value := strings.TrimSpace(match[1])
	value = strings.Trim(value, "*_` ")
	if len(value) > 220 {
		value = value[:220] + "…"
	}
	return value
}

type ghContentEntry struct {
	Name string `json:"name"`
	Path string `json:"path"`
	Size int64  `json:"size"`
	Type string `json:"type"`
}

func (a *API) repositoryCards(ctx context.Context, repositoryID, remoteIdentity string) ([]cardSummary, error) {
	repoPath, ok := ghRepoPath(remoteIdentity)
	if !ok {
		return []cardSummary{}, nil
	}
	listing, err := runGH(ctx, "api", "repos/"+repoPath+"/contents/"+cardsDir)
	if err != nil {
		// A repository without knowledge/cards is normal, not an error.
		return []cardSummary{}, nil
	}
	var entries []ghContentEntry
	if err := json.Unmarshal(listing, &entries); err != nil {
		return nil, err
	}
	cards := make([]cardSummary, 0, len(entries))
	for _, entry := range entries {
		if entry.Type != "file" || !strings.HasSuffix(entry.Name, ".md") {
			continue
		}
		card := cardSummary{
			RepositoryID:       repositoryID,
			RepositoryIdentity: remoteIdentity,
			Path:               entry.Path,
			Name:               strings.TrimSuffix(entry.Name, ".md"),
			Size:               entry.Size,
			GitHubURL:          "https://github.com/" + repoPath + "/blob/HEAD/" + entry.Path,
		}
		if content, err := a.cardContent(ctx, remoteIdentity, entry.Path, 16*1024); err == nil {
			card.Status = firstMatch(statusPattern, content)
			card.NextAction = firstMatch(nextPattern, content)
		}
		cards = append(cards, card)
	}
	return cards, nil
}

func (a *API) cardContent(ctx context.Context, remoteIdentity, path string, limit int) (string, error) {
	repoPath, ok := ghRepoPath(remoteIdentity)
	if !ok {
		return "", nil
	}
	raw, err := runGH(ctx, "api", "repos/"+repoPath+"/contents/"+path)
	if err != nil {
		return "", err
	}
	var payload struct {
		Content  string `json:"content"`
		Encoding string `json:"encoding"`
	}
	if err := json.Unmarshal(raw, &payload); err != nil {
		return "", err
	}
	var text string
	if payload.Encoding == "base64" {
		decoded, err := base64.StdEncoding.DecodeString(strings.ReplaceAll(payload.Content, "\n", ""))
		if err != nil {
			return "", err
		}
		text = string(decoded)
	} else {
		text = payload.Content
	}
	if limit > 0 && len(text) > limit {
		text = text[:limit]
	}
	return text, nil
}

func (a *API) listCards(w http.ResponseWriter, r *http.Request) {
	repositories, err := a.store.ManagedRepositories(r.Context())
	if err != nil {
		writeError(w, err)
		return
	}
	all := []cardSummary{}
	for _, repository := range repositories {
		if !repository.Enabled {
			continue
		}
		cardsCacheMu.Lock()
		entry, cached := cardsCache[repository.ID]
		cardsCacheMu.Unlock()
		if cached && time.Since(entry.fetched) < cardsCacheTTL {
			all = append(all, entry.cards...)
			continue
		}
		cards, err := a.repositoryCards(r.Context(), repository.ID, repository.RemoteIdentity)
		if err != nil {
			a.logger.Warn("cards_fetch_failed", "repository", repository.RemoteIdentity, "error", err)
			cards = []cardSummary{}
		}
		cardsCacheMu.Lock()
		cardsCache[repository.ID] = cardsCacheEntry{fetched: time.Now(), cards: cards}
		cardsCacheMu.Unlock()
		all = append(all, cards...)
	}
	writeJSON(w, http.StatusOK, map[string]any{"cards": all})
}

func (a *API) getCard(w http.ResponseWriter, r *http.Request) {
	repositoryID := r.URL.Query().Get("repository_id")
	path := r.URL.Query().Get("path")
	if repositoryID == "" || path == "" ||
		!strings.HasPrefix(path, cardsDir+"/") || strings.Contains(path, "..") {
		writeError(w, invalid("invalid_card", "repository_id and a knowledge/cards path are required"))
		return
	}
	repositories, err := a.store.ManagedRepositories(r.Context())
	if err != nil {
		writeError(w, err)
		return
	}
	var remoteIdentity string
	for _, repository := range repositories {
		if repository.ID == repositoryID {
			remoteIdentity = repository.RemoteIdentity
		}
	}
	if remoteIdentity == "" {
		writeError(w, invalid("repository_not_found", "unknown repository_id"))
		return
	}
	content, err := a.cardContent(r.Context(), remoteIdentity, path, 256*1024)
	if err != nil {
		writeError(w, unavailable(err))
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"content": content})
}
