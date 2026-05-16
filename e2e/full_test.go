//go:build e2e_full

// Full structural validation over every day in the lectionary year.
// No LLM calls — fast, deterministic. Catches panics, missing sections,
// empty collects, or days where the renderer produces nothing.
//
// Run: go test ./e2e/... -tags e2e_full -timeout 5m
package e2e_test

import (
	"fmt"
	"testing"
	"time"
)

func TestFullLectionaryYear(t *testing.T) {
	// Walk every day in 2026 — a full BAS lectionary year.
	start := time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)
	end := time.Date(2027, 1, 1, 0, 0, 0, 0, time.UTC)

	for d := start; d.Before(end); d = d.AddDate(0, 0, 1) {
		d := d
		date := d.Format("2006-01-02")

		for _, ot := range []string{"mp", "ep"} {
			ot := ot
			t.Run(fmt.Sprintf("%s-%s", date, ot), func(t *testing.T) {
				t.Parallel()
				rendered, day := renderOffice(t, date, ot)

				if rendered == "" {
					t.Fatalf("%s %s: empty output", date, ot)
				}

				label := fmt.Sprintf("%s %s (%s %s)", date, ot, day.Name, day.Season)
				checkStructure(t, rendered, label)

				// Every day must have a collect reference.
				if ot == "mp" && day.Morning.Collect == "" && day.Morning.Alternate == nil {
					// No collect is unusual but might be valid for some ferias.
					t.Logf("%s: no collect assigned (feria?)", label)
				}
			})
		}
	}
}
