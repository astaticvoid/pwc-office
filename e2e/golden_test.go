//go:build e2e_full

// Golden-file snapshot tests for the office renderer.
// On first run (no golden file present): writes the rendered output and passes.
// On subsequent runs: diffs against the golden file and fails on any change.
//
// Run:           go test ./e2e/... -tags e2e_full -run TestGolden
// Update golden: go test ./e2e/... -tags e2e_full -run TestGolden -update
package e2e_test

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

var updateGolden = flag.Bool("update", false, "overwrite golden files with current output")

// goldenCases combines the smoke dates and a representative seasonal set.
var goldenCases = []struct {
	name string
	date string
	ot   string
}{
	// Smoke dates
	{"EasterMP", "2026-04-05", "mp"},
	{"EasterEP", "2026-04-05", "ep"},
	{"LentMP", "2026-03-08", "mp"},
	{"FeastDayMP", "2026-05-15", "mp"},
	// One representative per named season
	{"AdventMP", "2026-11-29", "mp"},
	{"AdventEP", "2026-11-29", "ep"},
	{"ChristmasMP", "2025-12-28", "mp"},
	{"EpiphanyMP", "2026-01-11", "mp"},
	{"PassiontideMP", "2026-03-29", "mp"},
	{"EasterSeasonMP", "2026-04-19", "mp"},
	{"PentecostMP", "2026-05-24", "mp"},
	{"AllSaintsMP", "2026-11-01", "mp"},
	// OrdinaryTime
	{"OrdinaryTimeSundayMP", "2026-06-07", "mp"},
	{"OrdinaryTimeMondayMP", "2026-06-08", "mp"},
}

func TestGolden(t *testing.T) {
	goldenDir := filepath.Join("testdata", "golden")
	if err := os.MkdirAll(goldenDir, 0755); err != nil {
		t.Fatalf("create golden dir: %v", err)
	}

	for _, tc := range goldenCases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			rendered, day := renderOffice(t, tc.date, tc.ot)
			t.Logf("Day: %s | Season: %s", day.Name, day.Season)

			goldenPath := filepath.Join(goldenDir, fmt.Sprintf("%s-%s.md", tc.date, tc.ot))

			if *updateGolden {
				if err := os.WriteFile(goldenPath, []byte(rendered), 0644); err != nil {
					t.Fatalf("write golden %s: %v", goldenPath, err)
				}
				t.Logf("updated golden: %s", goldenPath)
				return
			}

			existing, err := os.ReadFile(goldenPath)
			if os.IsNotExist(err) {
				// First run — write and pass.
				if err := os.WriteFile(goldenPath, []byte(rendered), 0644); err != nil {
					t.Fatalf("write golden %s: %v", goldenPath, err)
				}
				t.Logf("created golden: %s", goldenPath)
				return
			}
			if err != nil {
				t.Fatalf("read golden %s: %v", goldenPath, err)
			}

			if string(existing) != rendered {
				t.Errorf("golden mismatch for %s %s:\n%s", tc.date, tc.ot,
					diffSummary(string(existing), rendered))
			}
		})
	}
}

// diffSummary produces a compact diff of two multi-line strings.
func diffSummary(want, got string) string {
	wantLines := strings.Split(want, "\n")
	gotLines := strings.Split(got, "\n")
	var sb strings.Builder
	maxLines := len(wantLines)
	if len(gotLines) > maxLines {
		maxLines = len(gotLines)
	}
	shown := 0
	for i := 0; i < maxLines && shown < 10; i++ {
		wl, gl := "", ""
		if i < len(wantLines) {
			wl = wantLines[i]
		}
		if i < len(gotLines) {
			gl = gotLines[i]
		}
		if wl != gl {
			sb.WriteString(fmt.Sprintf("line %d:\n  want: %q\n   got: %q\n", i+1, wl, gl))
			shown++
		}
	}
	if shown == 10 {
		sb.WriteString("(first 10 differing lines shown)\n")
	}
	return sb.String()
}
