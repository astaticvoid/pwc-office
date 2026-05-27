package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	lectionary "github.com/astaticvoid/pwc-office"
	"github.com/astaticvoid/pwc-office/internal/office"
)

func main() {
	translation := flag.String("translation", "nrsvue", "scripture translation: nrsvue, kjv, api")
	flag.Usage = func() {
		fmt.Fprintln(os.Stderr, "usage: dailyoffice [--translation nrsvue|kjv|api] [mp|ep] [YYYY-MM-DD]")
	}
	flag.Parse()

	loadDotEnv()

	officeType := "mp"
	dateStr := ""
	switch flag.NArg() {
	case 0:
	case 1:
		officeType = flag.Arg(0)
	case 2:
		officeType = flag.Arg(0)
		dateStr = flag.Arg(1)
	default:
		flag.Usage()
		os.Exit(1)
	}

	if officeType != "mp" && officeType != "ep" {
		fmt.Fprintln(os.Stderr, "office must be mp or ep")
		os.Exit(1)
	}

	var d time.Time
	if dateStr == "" {
		d = time.Now()
	} else {
		var err error
		d, err = time.Parse("2006-01-02", dateStr)
		if err != nil {
			fmt.Fprintf(os.Stderr, "invalid date %q: use YYYY-MM-DD\n", dateStr)
			os.Exit(1)
		}
	}

	l, err := lectionary.Load()
	if err != nil {
		fmt.Fprintf(os.Stderr, "loading lectionary: %v\n", err)
		os.Exit(1)
	}

	ps, err := lectionary.LoadPsalter()
	if err != nil {
		fmt.Fprintf(os.Stderr, "loading psalter: %v\n", err)
		os.Exit(1)
	}

	day, err := l.Lookup(d)
	if err != nil {
		fmt.Fprintf(os.Stderr, "%v\n", err)
		os.Exit(1)
	}

	var bible lectionary.BibleSource
	switch *translation {
	case "kjv":
		bible = lectionary.KJV()
	case "nrsvue":
		dir := filepath.Join(xdgDataDir(), "pwc_office", "translations", "nrsvue")
		lb, err := lectionary.LoadLocalBible("nrsvue", dir)
		if err != nil {
			fmt.Fprintf(os.Stderr, "loading nrsvue: %v\n(copy data/translations/nrsvue/*.json to %s)\n", err, dir)
			os.Exit(1)
		}
		bible = lb
	case "api":
		ab, err := lectionary.LoadBible(os.Getenv("BIBLE_API_KEY"))
		if err != nil {
			fmt.Fprintf(os.Stderr, "loading bible API: %v\n", err)
			os.Exit(1)
		}
		if ab == nil {
			fmt.Fprintln(os.Stderr, "--translation api requires BIBLE_API_KEY to be set")
			os.Exit(1)
		}
		bible = ab
	default:
		fmt.Fprintf(os.Stderr, "unknown translation %q: choose nrsvue, kjv, or api\n", *translation)
		os.Exit(1)
	}

	collects, err := lectionary.LoadCollects()
	if err != nil {
		fmt.Fprintf(os.Stderr, "loading collects: %v\n", err)
		os.Exit(1)
	}

	forms, err := lectionary.LoadForms()
	if err != nil {
		fmt.Fprintf(os.Stderr, "loading forms: %v\n", err)
		os.Exit(1)
	}

	fmt.Print(office.Render(day, officeType, ps, bible, collects, forms, l.Bounds))
}

// xdgDataDir returns $XDG_DATA_HOME or ~/.local/share.
func xdgDataDir() string {
	if d := os.Getenv("XDG_DATA_HOME"); d != "" {
		return d
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return filepath.Join(".", ".local", "share")
	}
	return filepath.Join(home, ".local", "share")
}

// loadDotEnv reads key=value pairs from .env in the current directory.
// Only sets variables that are not already set in the environment.
func loadDotEnv() {
	data, err := os.ReadFile(".env")
	if err != nil {
		return
	}
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		idx := strings.Index(line, "=")
		if idx <= 0 {
			continue
		}
		key := strings.TrimSpace(line[:idx])
		val := strings.TrimSpace(line[idx+1:])
		if os.Getenv(key) == "" {
			os.Setenv(key, val)
		}
	}
}
