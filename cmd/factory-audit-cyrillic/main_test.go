package main

import (
	"context"
	"io"
	"strings"
	"testing"
)

func TestRunRequiresExplicitSnapshotAndSources(t *testing.T) {
	for _, arguments := range [][]string{nil, {"--database", "snapshot.sqlite3"}, {"unexpected"}} {
		if err := run(context.Background(), arguments, io.Discard); err == nil ||
			!strings.Contains(err.Error(), "--database SNAPSHOT --sources SOURCES.json") {
			t.Fatalf("run(%v) error = %v", arguments, err)
		}
	}
}
