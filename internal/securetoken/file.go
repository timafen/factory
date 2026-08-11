package securetoken

import (
	"crypto/rand"
	"encoding/base64"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
)

func Validate(value string) error {
	decoded, err := base64.RawURLEncoding.DecodeString(value)
	if err != nil || len(decoded) != 32 {
		return errors.New("credential must contain 32 random bytes")
	}
	return nil
}

func Read(path string) (string, error) {
	before, err := os.Lstat(path)
	if err != nil {
		return "", err
	}
	if !before.Mode().IsRegular() || before.Mode()&os.ModeSymlink != 0 || before.Mode().Perm() != 0o600 {
		return "", errors.New("credential must be a regular non-symlink file with mode 0600")
	}
	file, err := os.Open(path)
	if err != nil {
		return "", err
	}
	after, statErr := file.Stat()
	if statErr != nil || !os.SameFile(before, after) {
		file.Close()
		return "", errors.New("credential changed while it was opened")
	}
	body, readErr := io.ReadAll(io.LimitReader(file, 1025))
	closeErr := file.Close()
	if readErr != nil || closeErr != nil {
		return "", errors.Join(readErr, closeErr)
	}
	if len(body) > 1024 {
		return "", errors.New("credential is too large")
	}
	value := strings.TrimSuffix(string(body), "\n")
	if err := Validate(value); err != nil {
		return "", err
	}
	return value, nil
}

func LoadOrCreate(path string) (string, error) {
	value, err := Read(path)
	if err == nil {
		return value, nil
	}
	if !errors.Is(err, os.ErrNotExist) {
		return "", err
	}
	var body [32]byte
	if _, err := rand.Read(body[:]); err != nil {
		return "", fmt.Errorf("generate credential: %w", err)
	}
	value = base64.RawURLEncoding.EncodeToString(body[:])
	file, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
	if errors.Is(err, os.ErrExist) {
		return Read(path)
	}
	if err != nil {
		return "", err
	}
	remove := true
	defer func() {
		if remove {
			_ = os.Remove(path)
		}
	}()
	if _, err := io.WriteString(file, value+"\n"); err != nil {
		file.Close()
		return "", err
	}
	if err := file.Sync(); err != nil {
		file.Close()
		return "", err
	}
	if err := file.Close(); err != nil {
		return "", err
	}
	directory, err := os.Open(filepath.Dir(path))
	if err != nil {
		return "", err
	}
	syncErr := directory.Sync()
	closeErr := directory.Close()
	if syncErr != nil || closeErr != nil {
		return "", errors.Join(syncErr, closeErr)
	}
	remove = false
	return value, nil
}
