//go:build e2e_seasonal

// Run: go test ./e2e/... -tags e2e_seasonal
package e2e_test

import (
	"testing"

)

// seasonCase defines one representative day per liturgical season.
// The date must actually fall in the expected season per the lectionary.
type seasonCase struct {
	name       string
	date       string
	officeType string
}

// seasonalCases covers every liturgical form available in the YAML:
// 8 named seasons × 2 offices, plus OrdinaryTime by weekday × 2 offices.
// Dates verified against the lectionary — see TestVerifySeasonDates.
var seasonalCases = []seasonCase{
	// Named seasons
	{"Advent-MP", "2026-11-29", "mp"},
	{"Advent-EP", "2026-11-29", "ep"},
	{"Christmas-MP", "2025-12-28", "mp"}, // Dec 25 returns Advent in lectionary; use Dec 28
	{"Christmas-EP", "2025-12-28", "ep"},
	{"Epiphany-MP", "2026-01-11", "mp"},
	{"Epiphany-EP", "2026-01-11", "ep"},
	{"Lent-MP", "2026-03-08", "mp"},
	{"Lent-EP", "2026-03-08", "ep"},
	{"Passiontide-MP", "2026-03-29", "mp"},
	{"Passiontide-EP", "2026-03-29", "ep"},
	{"Easter-MP", "2026-04-19", "mp"},
	{"Easter-EP", "2026-04-19", "ep"},
	{"Pentecost-MP", "2026-05-24", "mp"},
	{"Pentecost-EP", "2026-05-24", "ep"},
	{"AllSaints-MP", "2026-11-01", "mp"},
	{"AllSaints-EP", "2026-11-01", "ep"},
	// OrdinaryTime — the BAS calls this the "Pentecost" season; forms are weekday-specific.
	// These six dates land on the correct weekday in ordinary time (June 2026).
	{"OrdinaryTime-Sunday-MP", "2026-06-07", "mp"},
	{"OrdinaryTime-Sunday-EP", "2026-06-07", "ep"},
	{"OrdinaryTime-Monday-MP", "2026-06-08", "mp"},
	{"OrdinaryTime-Monday-EP", "2026-06-08", "ep"},
	{"OrdinaryTime-Wednesday-MP", "2026-06-10", "mp"},
	{"OrdinaryTime-Wednesday-EP", "2026-06-10", "ep"},
	{"OrdinaryTime-Friday-MP", "2026-06-12", "mp"},
	{"OrdinaryTime-Friday-EP", "2026-06-12", "ep"},
	{"OrdinaryTime-Saturday-MP", "2026-06-13", "mp"},
	{"OrdinaryTime-Saturday-EP", "2026-06-13", "ep"},
}

func TestSeasonalOffices(t *testing.T) {
	for _, tc := range seasonalCases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			officeName := "Morning Prayer"
			if tc.officeType == "ep" {
				officeName = "Evening Prayer"
			}

			rendered, day := renderOffice(t, tc.date, tc.officeType)
			t.Logf("Day: %s | Season: %s | Rank: %s", day.Name, day.Season, day.Rank)

			checkStructure(t, rendered, tc.name)

			or := fetchOfficialReadings(t, tc.date, tc.officeType)
			verifyReadings(t, tc.name, rendered, or)
			eval := evalOffice(t, tc.date, day.Season.String(), officeName, rendered, or)
			reportEval(t, tc.name, eval)
		})
	}
}
