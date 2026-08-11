package worker

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/owainlewis/factory/internal/protocol"
)

const requestTimeout = 10 * time.Second

type APIError struct {
	Status  int
	Code    string
	Message string
}

func (err *APIError) Error() string {
	return fmt.Sprintf("control plane returned %d %s: %s", err.Status, err.Code, err.Message)
}

type client struct {
	baseURL             string
	http                *http.Client
	credentialMu        sync.RWMutex
	credential          string
	bootstrapCredential string
}

func newClient(server string, httpClient *http.Client) *client {
	if httpClient == nil {
		httpClient = &http.Client{}
	}
	return &client{baseURL: strings.TrimRight(server, "/"), http: httpClient}
}

func (client *client) register(ctx context.Context, workerID string, input protocol.WorkerRegistration) (protocol.Worker, string, error) {
	var worker protocol.Worker
	_, headers, err := client.requestWithResponse(ctx, http.MethodPut, "/api/v1/workers/"+url.PathEscape(workerID), input, &worker, true)
	if err != nil {
		return worker, "", err
	}
	credential := headers.Get(protocol.WorkerCredentialHeader)
	return worker, credential, nil
}

func (client *client) setWorkerCredential(credential string) {
	client.credentialMu.Lock()
	client.credential = credential
	client.credentialMu.Unlock()
}

func (client *client) setWorkerBootstrapCredential(credential string) {
	client.credentialMu.Lock()
	client.bootstrapCredential = credential
	client.credentialMu.Unlock()
}

func (client *client) workerCredential() string {
	client.credentialMu.RLock()
	defer client.credentialMu.RUnlock()
	return client.credential
}

func (client *client) workerBootstrapCredential() string {
	client.credentialMu.RLock()
	defer client.credentialMu.RUnlock()
	return client.bootstrapCredential
}

func (client *client) project(ctx context.Context, projectID string) (protocol.Project, error) {
	var project protocol.Project
	_, err := client.request(ctx, http.MethodGet, "/api/v1/projects/"+url.PathEscape(projectID), nil, &project)
	return project, err
}

func (client *client) verifyProject(ctx context.Context, workerID, projectID string, input protocol.ProjectVerificationRequest) error {
	_, _, err := client.requestWithResponse(ctx, http.MethodPost, "/api/v1/workers/"+url.PathEscape(workerID)+"/projects/"+url.PathEscape(projectID)+"/verification", input, nil, true)
	return err
}

func (client *client) claim(ctx context.Context, workerID string, input protocol.ClaimRequest, minimumBackoff, maximumBackoff time.Duration) (*protocol.Claim, error) {
	var claim protocol.Claim
	status, err := client.retry(ctx, http.MethodPost,
		"/api/v1/workers/"+url.PathEscape(workerID)+"/claims", input, &claim, minimumBackoff, maximumBackoff)
	if err != nil {
		return nil, err
	}
	if status == http.StatusNoContent {
		return nil, nil
	}
	return &claim, nil
}

func (client *client) start(ctx context.Context, attemptID string, input protocol.StartAttemptRequest) (protocol.Attempt, error) {
	var attempt protocol.Attempt
	_, err := client.retry(ctx, http.MethodPost, "/api/v1/attempts/"+url.PathEscape(attemptID)+"/start",
		input, &attempt, time.Second, 5*time.Second)
	return attempt, err
}

func (client *client) heartbeat(ctx context.Context, attemptID, token string) (protocol.HeartbeatResponse, error) {
	var heartbeat protocol.HeartbeatResponse
	_, err := client.request(ctx, http.MethodPut, "/api/v1/attempts/"+url.PathEscape(attemptID)+"/heartbeat",
		protocol.LeaseRequest{LeaseToken: token}, &heartbeat)
	return heartbeat, err
}

func (client *client) attempt(ctx context.Context, attemptID string) (protocol.Attempt, error) {
	var attempt protocol.Attempt
	_, err := client.request(ctx, http.MethodGet, "/api/v1/attempts/"+url.PathEscape(attemptID), nil, &attempt)
	return attempt, err
}

func (client *client) events(ctx context.Context, attemptID string, input protocol.EventBatchRequest) error {
	_, err := client.request(ctx, http.MethodPost, "/api/v1/attempts/"+url.PathEscape(attemptID)+"/events", input, nil)
	return err
}

func (client *client) complete(ctx context.Context, attemptID string, input protocol.CompleteAttemptRequest) (protocol.Attempt, error) {
	input = boundedCompletionRequest(input)
	var attempt protocol.Attempt
	_, err := client.retry(ctx, http.MethodPost, "/api/v1/attempts/"+url.PathEscape(attemptID)+"/complete",
		input, &attempt, time.Second, 5*time.Second)
	return attempt, err
}

func (client *client) attachment(ctx context.Context, attemptID, attachmentID, token string) (io.ReadCloser, string, error) {
	requestContext, cancel := context.WithTimeout(ctx, requestTimeout)
	request, err := http.NewRequestWithContext(requestContext, http.MethodGet, client.baseURL+"/api/v1/attempts/"+url.PathEscape(attemptID)+"/attachments/"+url.PathEscape(attachmentID), nil)
	if err != nil {
		cancel()
		return nil, "", err
	}
	request.Header.Set("X-Factory-Lease-Token", token)
	response, err := client.http.Do(request)
	if err != nil {
		cancel()
		return nil, "", err
	}
	if response.StatusCode != http.StatusOK {
		response.Body.Close()
		cancel()
		return nil, "", fmt.Errorf("attachment download returned %d", response.StatusCode)
	}
	return &cancelReadCloser{ReadCloser: response.Body, cancel: cancel}, response.Header.Get("X-Content-SHA256"), nil
}

type cancelReadCloser struct {
	io.ReadCloser
	cancel context.CancelFunc
}

func (c *cancelReadCloser) Close() error { err := c.ReadCloser.Close(); c.cancel(); return err }

func boundedCompletionRequest(input protocol.CompleteAttemptRequest) protocol.CompleteAttemptRequest {
	input.Result = boundedText(strings.ToValidUTF8(input.Result, "\uFFFD"), protocol.MaxResultBytes)
	input.Error = boundedText(strings.ToValidUTF8(input.Error, "\uFFFD"), protocol.MaxErrorBytes)
	if completionRequestFits(input) {
		return input
	}
	input.Result = largestCompletionField(input, input.Result, true)
	if completionRequestFits(input) {
		return input
	}
	input.Error = largestCompletionField(input, input.Error, false)
	return input
}

func largestCompletionField(input protocol.CompleteAttemptRequest, value string, result bool) string {
	low, high := 0, len(value)
	for low < high {
		middle := low + (high-low+1)/2
		candidate := boundedText(value, middle)
		if result {
			input.Result = candidate
		} else {
			input.Error = candidate
		}
		if completionRequestFits(input) {
			low = middle
		} else {
			high = middle - 1
		}
	}
	return boundedText(value, low)
}

func completionRequestFits(input protocol.CompleteAttemptRequest) bool {
	body, err := json.Marshal(input)
	return err == nil && len(body) <= protocol.MaxBodyBytes
}

func (client *client) retry(
	ctx context.Context,
	method string,
	path string,
	input any,
	output any,
	minimumBackoff time.Duration,
	maximumBackoff time.Duration,
) (int, error) {
	backoff := minimumBackoff
	for {
		status, err := client.request(ctx, method, path, input, output)
		if err == nil {
			return status, nil
		}
		var apiError *APIError
		if errors.As(err, &apiError) && apiError.Status < 500 {
			return status, err
		}
		timer := time.NewTimer(backoff)
		select {
		case <-ctx.Done():
			timer.Stop()
			return 0, ctx.Err()
		case <-timer.C:
		}
		backoff *= 2
		if backoff > maximumBackoff {
			backoff = maximumBackoff
		}
	}
}

func (client *client) request(ctx context.Context, method, path string, input any, output any) (int, error) {
	status, _, err := client.requestWithResponse(ctx, method, path, input, output, false)
	return status, err
}

func (client *client) requestWithResponse(ctx context.Context, method, path string, input any, output any, authenticated bool) (int, http.Header, error) {
	body, err := json.Marshal(input)
	if err != nil {
		return 0, nil, fmt.Errorf("encode request: %w", err)
	}
	requestContext, cancel := context.WithTimeout(ctx, requestTimeout)
	defer cancel()
	request, err := http.NewRequestWithContext(requestContext, method, client.baseURL+path, bytes.NewReader(body))
	if err != nil {
		return 0, nil, fmt.Errorf("create request: %w", err)
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Accept", "application/json")
	if authenticated {
		if credential := client.workerCredential(); credential != "" {
			request.Header.Set(protocol.WorkerCredentialHeader, credential)
		} else if credential := client.workerBootstrapCredential(); credential != "" {
			request.Header.Set(protocol.WorkerBootstrapCredentialHeader, credential)
		}
	}
	response, err := client.http.Do(request)
	if err != nil {
		return 0, nil, fmt.Errorf("send request: %w", err)
	}
	defer response.Body.Close()
	responseBody, err := io.ReadAll(io.LimitReader(response.Body, protocol.MaxBodyBytes+1))
	if err != nil {
		return response.StatusCode, response.Header, fmt.Errorf("read response: %w", err)
	}
	if len(responseBody) > protocol.MaxBodyBytes {
		return response.StatusCode, response.Header, errors.New("control-plane response exceeds 1 MiB")
	}
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		var errorBody protocol.ErrorBody
		if err := json.Unmarshal(responseBody, &errorBody); err != nil {
			return response.StatusCode, response.Header, &APIError{
				Status: response.StatusCode, Code: "invalid_error_response", Message: strings.TrimSpace(string(responseBody)),
			}
		}
		return response.StatusCode, response.Header, &APIError{
			Status: response.StatusCode, Code: errorBody.Error.Code, Message: errorBody.Error.Message,
		}
	}
	if response.StatusCode == http.StatusNoContent || output == nil {
		return response.StatusCode, response.Header, nil
	}
	decoder := json.NewDecoder(bytes.NewReader(responseBody))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(output); err != nil {
		return response.StatusCode, response.Header, fmt.Errorf("decode response: %w", err)
	}
	return response.StatusCode, response.Header, nil
}
