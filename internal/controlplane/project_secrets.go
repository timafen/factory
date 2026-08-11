package controlplane

import (
	"bufio"
	"errors"
	"fmt"
	"os"
	"os/user"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"

	"github.com/owainlewis/factory/internal/protocol"
)

func (s *Store) ResolveProjectSecrets(project protocol.Project, environment string) ([]protocol.ProjectSecretStatus, error) {
	var required []string
	for _, candidate := range project.Environments {
		if candidate.Name == environment {
			required = candidate.RequiredSecrets
			break
		}
	}
	if required == nil {
		return nil, ErrNotFound
	}
	if !validUUID(project.ID) || (environment != "staging" && environment != "production") {
		return nil, errors.New("invalid server-controlled secret path")
	}
	path := filepath.Join(s.projectSecretRoot, project.ID, environment+".env")
	info, err := os.Lstat(path)
	statuses := make([]protocol.ProjectSecretStatus, len(required))
	for i, name := range required {
		statuses[i].Name = name
	}
	if err != nil {
		return statuses, errors.New("secret file is missing")
	}
	if !info.Mode().IsRegular() || info.Mode()&os.ModeSymlink != 0 || info.Mode().Perm() != 0o640 {
		return statuses, errors.New("secret file must be a regular non-symlink file with mode 0640")
	}
	file, err := os.Open(path)
	if err != nil {
		return statuses, errors.New("secret file cannot be read")
	}
	defer file.Close()
	openedInfo, err := file.Stat()
	if err != nil || !os.SameFile(info, openedInfo) {
		return statuses, errors.New("secret file changed while it was being verified")
	}
	stat, ok := openedInfo.Sys().(*syscall.Stat_t)
	if !ok || stat.Uid != s.projectSecretOwnerUID {
		return statuses, errors.New("secret file must be owned by root")
	}
	group, err := user.LookupGroup(project.ExecutorGroup)
	if err != nil {
		return statuses, errors.New("server executor group is unavailable")
	}
	groupID, err := strconv.ParseUint(group.Gid, 10, 32)
	if err != nil || uint32(groupID) != stat.Gid {
		return statuses, errors.New("secret file group does not match the server project allowlist")
	}
	present := map[string]bool{}
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		name, _, ok := strings.Cut(line, "=")
		name = strings.TrimSpace(strings.TrimPrefix(name, "export "))
		if ok && validSecretName(name) {
			present[name] = true
		}
	}
	if err := scanner.Err(); err != nil {
		return statuses, fmt.Errorf("read secret names: %w", err)
	}
	missing := false
	for i, name := range required {
		statuses[i].Present = present[name]
		missing = missing || !present[name]
	}
	if missing {
		return statuses, errors.New("one or more required secrets are missing")
	}
	return statuses, nil
}
