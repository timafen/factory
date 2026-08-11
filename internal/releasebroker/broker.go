package releasebroker

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"os/exec"
	"regexp"
	"sync"
)

const MaxBodyBytes = 64 << 10

var (
	operationIDPattern = regexp.MustCompile(`^[a-z0-9][a-z0-9-]{0,127}$`)
	commitSHAPattern   = regexp.MustCompile(`^[0-9a-f]{40}([0-9a-f]{24})?$`)
)

type Request struct {
	OperationID string `json:"operation_id"`
	Adapter     string `json:"adapter"`
	CommitSHA   string `json:"commit_sha"`
}

type Response struct {
	Status string `json:"status"`
}

type Executor interface {
	Execute(context.Context, string, string) string
}

type FXExecutor struct {
	Executable string
}

func (executor FXExecutor) Execute(ctx context.Context, adapter, sha string) string {
	executable := executor.Executable
	if executable == "" {
		executable = "/usr/local/bin/fx"
	}
	args, ok := invocation(adapter, sha)
	if !ok {
		return "rollback_failed"
	}
	command := exec.CommandContext(ctx, executable, args...)
	command.Env = []string{
		"LANG=C.UTF-8",
		"LC_ALL=C.UTF-8",
		"PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
	}
	err := command.Run()
	if err == nil {
		return "succeeded"
	}
	var exitError *exec.ExitError
	if (adapter == "fx-factory-release" || adapter == "tarser-staging-deploy-release") && errors.As(err, &exitError) && exitError.ExitCode() == 6 {
		return "release_failed_rolled_back"
	}
	return "rollback_failed"
}

func invocation(adapter, sha string) ([]string, bool) {
	switch adapter {
	case "fx-factory-release":
		if !commitSHAPattern.MatchString(sha) {
			return nil, false
		}
		return []string{"factory", "release", sha}, true
	case "fx-factory-rollback":
		if !commitSHAPattern.MatchString(sha) {
			return nil, false
		}
		return []string{"factory", "rollback"}, true
	case "tarser-staging-deploy-release":
		if !commitSHAPattern.MatchString(sha) {
			return nil, false
		}
		return []string{"staging", "release", sha}, true
	case "tarser-staging-auto-rollback":
		if !commitSHAPattern.MatchString(sha) {
			return nil, false
		}
		return []string{"staging", "rollback"}, true
	default:
		return nil, false
	}
}

type operation struct {
	request Request
	status  string
}

type Broker struct {
	executor Executor
	mu       sync.Mutex
	active   string
	items    map[string]*operation
}

func New(executor Executor) *Broker {
	return &Broker{executor: executor, items: make(map[string]*operation)}
}

func (broker *Broker) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("POST /v1/operations", broker.start)
	mux.HandleFunc("GET /v1/operations/{operation_id}", broker.status)
	return mux
}

func (broker *Broker) start(response http.ResponseWriter, request *http.Request) {
	request.Body = http.MaxBytesReader(response, request.Body, MaxBodyBytes)
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	var input Request
	if err := decoder.Decode(&input); err != nil {
		http.Error(response, "invalid request", http.StatusBadRequest)
		return
	}
	if !operationIDPattern.MatchString(input.OperationID) || !commitSHAPattern.MatchString(input.CommitSHA) {
		http.Error(response, "invalid operation identity", http.StatusBadRequest)
		return
	}
	if _, ok := invocation(input.Adapter, input.CommitSHA); !ok {
		http.Error(response, "adapter is not allowed", http.StatusBadRequest)
		return
	}

	broker.mu.Lock()
	if existing := broker.items[input.OperationID]; existing != nil {
		if existing.request != input {
			broker.mu.Unlock()
			http.Error(response, "operation identity already has different immutable input", http.StatusConflict)
			return
		}
		status := existing.status
		broker.mu.Unlock()
		writeJSON(response, http.StatusOK, Response{Status: status})
		return
	}
	if broker.active != "" {
		broker.mu.Unlock()
		http.Error(response, "another privileged operation is running", http.StatusConflict)
		return
	}
	item := &operation{request: input, status: "running"}
	broker.items[input.OperationID] = item
	broker.active = input.OperationID
	broker.mu.Unlock()

	go func() {
		status := broker.executor.Execute(context.Background(), input.Adapter, input.CommitSHA)
		if status != "succeeded" && status != "release_failed_rolled_back" && status != "rollback_failed" {
			status = "rollback_failed"
		}
		broker.mu.Lock()
		item.status = status
		if broker.active == input.OperationID {
			broker.active = ""
		}
		broker.mu.Unlock()
	}()
	writeJSON(response, http.StatusAccepted, Response{Status: "running"})
}

func (broker *Broker) status(response http.ResponseWriter, request *http.Request) {
	id := request.PathValue("operation_id")
	if !operationIDPattern.MatchString(id) {
		http.Error(response, "invalid operation identity", http.StatusBadRequest)
		return
	}
	broker.mu.Lock()
	item := broker.items[id]
	if item == nil {
		broker.mu.Unlock()
		http.Error(response, "operation not found", http.StatusNotFound)
		return
	}
	status := item.status
	broker.mu.Unlock()
	writeJSON(response, http.StatusOK, Response{Status: status})
}

func writeJSON(response http.ResponseWriter, status int, value any) {
	response.Header().Set("Content-Type", "application/json")
	response.WriteHeader(status)
	_ = json.NewEncoder(response).Encode(value)
}
