package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"

	"github.com/owainlewis/factory/internal/cyrillicaudit"
)

func main() {
	if err := run(context.Background(), os.Args[1:], os.Stdout); err != nil {
		fmt.Fprintln(os.Stderr, "audit failed:", err)
		os.Exit(1)
	}
}

func run(ctx context.Context, arguments []string, output io.Writer) error {
	flags := flag.NewFlagSet("factory-audit-cyrillic", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	databasePath := flags.String("database", "", "immutable Factory SQLite snapshot")
	sourcesPath := flags.String("sources", "", "reviewed external sources JSON")
	if err := flags.Parse(arguments); err != nil {
		return err
	}
	if flags.NArg() != 0 || *databasePath == "" || *sourcesPath == "" {
		return errors.New("usage: factory-audit-cyrillic --database SNAPSHOT --sources SOURCES.json")
	}
	file, err := os.Open(*sourcesPath)
	if err != nil {
		return fmt.Errorf("open sources: %w", err)
	}
	defer file.Close()
	sources, err := cyrillicaudit.ReadSources(file)
	if err != nil {
		return err
	}
	report, err := cyrillicaudit.Audit(ctx, *databasePath, sources)
	if err != nil {
		return err
	}
	encoder := json.NewEncoder(output)
	encoder.SetIndent("", "  ")
	return encoder.Encode(report)
}
