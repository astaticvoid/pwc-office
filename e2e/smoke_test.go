//go:build e2e_smoke

// Package e2e_test contains end-to-end tests for the Daily Office renderer.
// Smoke tests cover well-known days with structural and reading verification.
//
// Run: go test ./e2e/... -tags e2e_smoke -timeout 10m
package e2e_test

import (
	"strings"
	"testing"
)

func TestSmokeEasterMP(t *testing.T) {

	const date = "2026-04-05"
	rendered, day := renderOffice(t, date, "mp")
	t.Logf("Day: %s | Season: %s | Rank: %s", day.Name, day.Season, day.Rank)
	checkStructure(t, rendered, "EasterMP")
	or := fetchOfficialReadings(t, date, "mp")
	verifyReadings(t, "EasterMP", rendered, or)
}

func TestSmokeEasterEP(t *testing.T) {

	const date = "2026-04-05"
	rendered, day := renderOffice(t, date, "ep")
	t.Logf("Day: %s | Season: %s | Rank: %s", day.Name, day.Season, day.Rank)
	checkStructure(t, rendered, "EasterEP")
	or := fetchOfficialReadings(t, date, "ep")
	verifyReadings(t, "EasterEP", rendered, or)
}

func TestSmokeLentMP(t *testing.T) {

	const date = "2026-03-08"
	rendered, day := renderOffice(t, date, "mp")
	t.Logf("Day: %s | Season: %s", day.Name, day.Season)
	checkStructure(t, rendered, "LentMP")
	if strings.Contains(strings.ToLower(rendered), "alleluia") {
		t.Error("LentMP: 'alleluia' found in Lenten office")
	}
	or := fetchOfficialReadings(t, date, "mp")
	verifyReadings(t, "LentMP", rendered, or)
}

func TestSmokeFeastDay(t *testing.T) {

	const date = "2026-05-15" // Saint Matthias (observed)
	rendered, day := renderOffice(t, date, "mp")
	t.Logf("Day: %s | Season: %s | Rank: %s", day.Name, day.Season, day.Rank)
	checkStructure(t, rendered, "FeastDayMP")
	if !strings.Contains(rendered, "Matthias") && !strings.Contains(rendered, "Judas") {
		t.Error("FeastDayMP: Saint Matthias collect not found in output")
	}
	or := fetchOfficialReadings(t, date, "mp")
	verifyReadings(t, "FeastDayMP", rendered, or)
}
