package controlplane

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"mime"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/owainlewis/factory/internal/protocol"
)

const pendingAttachmentTTL = 24 * time.Hour

var executableExtensions = map[string]bool{
	".exe": true, ".com": true, ".bat": true, ".cmd": true, ".msi": true,
	".scr": true, ".ps1": true, ".sh": true, ".app": true, ".apk": true,
}

func safeAttachmentName(name string) (string, error) {
	name = strings.TrimSpace(filepath.Base(strings.ReplaceAll(name, "\\", "/")))
	if name == "" || name == "." || name == ".." || strings.ContainsRune(name, 0) {
		return "", invalid("invalid_attachment_name", "у файла недопустимое имя")
	}
	if executableExtensions[strings.ToLower(filepath.Ext(name))] {
		return "", invalid("executable_attachment", fmt.Sprintf("файл %q является исполняемым и не принимается", name))
	}
	return name, nil
}

func (s *Store) UploadAttachment(ctx context.Context, requestKey, name, contentType string, source io.Reader) (protocol.TaskAttachment, error) {
	requestKey = strings.TrimSpace(requestKey)
	if requestKey == "" || len(requestKey) > 200 {
		return protocol.TaskAttachment{}, invalid("invalid_request_key", "request_key is required")
	}
	name, err := safeAttachmentName(name)
	if err != nil {
		return protocol.TaskAttachment{}, err
	}
	var count int
	if err := s.db.QueryRowContext(ctx, `SELECT COUNT(*) FROM task_attachments WHERE request_key = ? AND task_id IS NULL`, requestKey).Scan(&count); err != nil {
		return protocol.TaskAttachment{}, unavailable(err)
	}
	if count >= protocol.MaxTaskAttachments {
		return protocol.TaskAttachment{}, invalid("too_many_attachments", "к задаче можно прикрепить не больше 5 файлов")
	}
	id, err := newID()
	if err != nil {
		return protocol.TaskAttachment{}, unavailable(err)
	}
	dir := filepath.Join(s.attachmentRoot, "pending", id)
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return protocol.TaskAttachment{}, unavailable(err)
	}
	path := filepath.Join(dir, name)
	f, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
	if err != nil {
		return protocol.TaskAttachment{}, unavailable(err)
	}
	hash := sha256.New()
	written, copyErr := io.Copy(io.MultiWriter(f, hash), io.LimitReader(source, protocol.MaxAttachmentBytes+1))
	closeErr := f.Close()
	if copyErr != nil || closeErr != nil {
		os.RemoveAll(dir)
		return protocol.TaskAttachment{}, unavailable(errors.Join(copyErr, closeErr))
	}
	if written == 0 {
		os.RemoveAll(dir)
		return protocol.TaskAttachment{}, invalid("empty_attachment", fmt.Sprintf("файл %q пуст", name))
	}
	if written > protocol.MaxAttachmentBytes {
		os.RemoveAll(dir)
		return protocol.TaskAttachment{}, invalid("attachment_too_large", fmt.Sprintf("файл %q больше 10 МБ", name))
	}
	if contentType == "" {
		contentType = mime.TypeByExtension(filepath.Ext(name))
	}
	if contentType == "" {
		contentType = "application/octet-stream"
	}
	attachment := protocol.TaskAttachment{ID: id, Name: name, ContentType: contentType, Size: written, SHA256: hex.EncodeToString(hash.Sum(nil))}
	_, err = s.db.ExecContext(ctx, `INSERT INTO task_attachments(id, request_key, name, content_type, size, sha256, storage_path, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`, id, requestKey, name, contentType, written, attachment.SHA256, path, s.now().UnixMilli())
	if err != nil {
		os.RemoveAll(dir)
		return protocol.TaskAttachment{}, unavailable(err)
	}
	return attachment, nil
}

func attachmentRows(rows *sql.Rows) ([]protocol.TaskAttachment, error) {
	var values []protocol.TaskAttachment
	for rows.Next() {
		var a protocol.TaskAttachment
		if err := rows.Scan(&a.ID, &a.Name, &a.ContentType, &a.Size, &a.SHA256); err != nil {
			return nil, err
		}
		values = append(values, a)
	}
	return values, rows.Err()
}

func (s *Store) taskAttachments(ctx context.Context, taskID string) ([]protocol.TaskAttachment, error) {
	rows, err := s.db.QueryContext(ctx, `SELECT id,name,content_type,size,sha256 FROM task_attachments WHERE task_id=? ORDER BY created_at,id`, taskID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return attachmentRows(rows)
}

func (s *Store) DeletePendingAttachment(ctx context.Context, id, requestKey string) error {
	var path string
	err := s.db.QueryRowContext(ctx, `SELECT storage_path FROM task_attachments WHERE id=? AND request_key=? AND task_id IS NULL`, id, requestKey).Scan(&path)
	if errors.Is(err, sql.ErrNoRows) {
		return ErrNotFound
	}
	if err != nil {
		return unavailable(err)
	}
	if _, err := s.db.ExecContext(ctx, `DELETE FROM task_attachments WHERE id=? AND request_key=? AND task_id IS NULL`, id, requestKey); err != nil {
		return unavailable(err)
	}
	_ = os.RemoveAll(filepath.Dir(path))
	return nil
}

func (s *Store) cleanupPendingAttachments(ctx context.Context, before int64) error {
	rows, err := s.db.QueryContext(ctx, `SELECT id,storage_path FROM task_attachments WHERE task_id IS NULL AND created_at < ?`, before)
	if err != nil {
		return unavailable(err)
	}
	type stale struct{ id, path string }
	var values []stale
	for rows.Next() {
		var value stale
		if err := rows.Scan(&value.id, &value.path); err != nil {
			rows.Close()
			return unavailable(err)
		}
		values = append(values, value)
	}
	if err := rows.Close(); err != nil {
		return unavailable(err)
	}
	for _, value := range values {
		if _, err := s.db.ExecContext(ctx, `DELETE FROM task_attachments WHERE id=? AND task_id IS NULL`, value.id); err != nil {
			return unavailable(err)
		}
		_ = os.RemoveAll(filepath.Dir(value.path))
	}
	return nil
}

func (s *Store) AttachmentForAttempt(ctx context.Context, attemptID, attachmentID, leaseToken string) (string, protocol.TaskAttachment, error) {
	var path string
	var a protocol.TaskAttachment
	var leaseDigest []byte
	err := s.db.QueryRowContext(ctx, `SELECT ta.storage_path,ta.id,ta.name,ta.content_type,ta.size,ta.sha256,a.lease_digest FROM task_attachments ta JOIN executions e ON e.task_id=ta.task_id JOIN attempts a ON a.execution_id=e.id WHERE a.id=? AND ta.id=? AND a.state IN ('preparing','running')`, attemptID, attachmentID).Scan(&path, &a.ID, &a.Name, &a.ContentType, &a.Size, &a.SHA256, &leaseDigest)
	if errors.Is(err, sql.ErrNoRows) {
		return "", a, ErrNotFound
	}
	if err != nil {
		return "", a, unavailable(err)
	}
	want := sha256.Sum256([]byte(leaseToken))
	if !strings.EqualFold(hex.EncodeToString(leaseDigest), hex.EncodeToString(want[:])) {
		return "", a, conflict("lease_not_owner", "the claim no longer owns an active lease")
	}
	return path, a, nil
}
