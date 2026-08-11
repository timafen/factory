package worker

import (
	"encoding/base64"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
)

const workerCredentialFilename = "worker-credential"

func validateWorkerCredential(credential string) error {
	decoded, err := base64.RawURLEncoding.DecodeString(credential)
	if err != nil || len(decoded) != 32 {
		return errors.New("worker credential is invalid")
	}
	return nil
}

func loadWorkerCredential(directory string) (string, error) {
	path := filepath.Join(directory, workerCredentialFilename)
	info, err := os.Lstat(path)
	if errors.Is(err, os.ErrNotExist) {
		return "", nil
	}
	if err != nil {
		return "", fmt.Errorf("inspect worker credential: %w", err)
	}
	if !info.Mode().IsRegular() || info.Mode()&os.ModeSymlink != 0 || info.Mode().Perm() != 0o600 {
		return "", errors.New("worker credential must be a regular non-symlink file with mode 0600")
	}
	file, err := os.Open(path)
	if err != nil {
		return "", fmt.Errorf("open worker credential: %w", err)
	}
	body, readErr := io.ReadAll(io.LimitReader(file, 1025))
	closeErr := file.Close()
	if readErr != nil || closeErr != nil {
		return "", fmt.Errorf("read worker credential: %w", errors.Join(readErr, closeErr))
	}
	if len(body) > 1024 {
		return "", errors.New("worker credential is too large")
	}
	credential := strings.TrimSuffix(string(body), "\n")
	if err := validateWorkerCredential(credential); err != nil {
		return "", err
	}
	return credential, nil
}

func saveWorkerCredential(directory, credential string) error {
	if err := validateWorkerCredential(credential); err != nil {
		return err
	}
	temporary, err := os.CreateTemp(directory, ".worker-credential-*")
	if err != nil {
		return fmt.Errorf("create worker credential: %w", err)
	}
	temporaryPath := temporary.Name()
	cleanup := true
	defer func() {
		if cleanup {
			_ = os.Remove(temporaryPath)
		}
	}()
	if err := temporary.Chmod(0o600); err != nil {
		temporary.Close()
		return fmt.Errorf("protect worker credential: %w", err)
	}
	if _, err := io.WriteString(temporary, credential+"\n"); err != nil {
		temporary.Close()
		return fmt.Errorf("write worker credential: %w", err)
	}
	if err := temporary.Sync(); err != nil {
		temporary.Close()
		return fmt.Errorf("sync worker credential: %w", err)
	}
	if err := temporary.Close(); err != nil {
		return fmt.Errorf("close worker credential: %w", err)
	}
	path := filepath.Join(directory, workerCredentialFilename)
	if err := os.Rename(temporaryPath, path); err != nil {
		return fmt.Errorf("install worker credential: %w", err)
	}
	cleanup = false
	if err := syncDirectory(directory); err != nil {
		return fmt.Errorf("sync worker credential directory: %w", err)
	}
	return nil
}
