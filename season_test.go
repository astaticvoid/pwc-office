package lectionary

import (
	"testing"
	"time"
)

var bounds2026 = SeasonBounds{
	AdventI:      date(2025, 11, 30),
	Christmas:    date(2025, 12, 25),
	Epiphany:     date(2026, 1, 11), // Baptism of the Lord
	AshWednesday: date(2026, 2, 18),
	PalmSunday:   date(2026, 3, 29),
	Easter:       date(2026, 4, 5),
	Pentecost:    date(2026, 5, 24),
	AllSaints:    date(2026, 11, 1),
	AdventII:     date(2026, 11, 29),
	ChristmasII:  date(2026, 12, 25),
}

// fullBounds2026 mirrors data/season_bounds.json exactly — all fields populated.
// Used to test FormSeasonOf (office form lookup) and JS/Go parity.
var fullBounds2026 = SeasonBounds{
	AdventI:      date(2025, 11, 30),
	Christmas:    date(2025, 12, 25),
	Epiphany:     date(2026, 1, 11),  // Baptism of the Lord
	Presentation: date(2026, 2, 2),   // Candlemas — Epiphany form ends
	AshWednesday: date(2026, 2, 18),
	Passiontide:  date(2026, 3, 22),  // 5th Sunday in Lent (Passion Sunday)
	PalmSunday:   date(2026, 3, 29),
	Easter:       date(2026, 4, 5),
	Ascension:    date(2026, 5, 14),  // Pentecost form starts
	Pentecost:    date(2026, 5, 24),
	TrinityS:     date(2026, 5, 31),  // Pentecost form ends (day after → OrdinaryTime)
	AllSaints:    date(2026, 11, 1),
	AdventII:     date(2026, 11, 29),
	ChristmasII:  date(2026, 12, 25),
}

func date(y, m, d int) time.Time {
	return time.Date(y, time.Month(m), d, 0, 0, 0, 0, time.UTC)
}

func TestSeasonOf(t *testing.T) {
	tests := []struct {
		date   time.Time
		season Season
		dow    time.Weekday
		label  string
	}{
		// Advent
		{date(2025, 11, 30), Advent, time.Sunday, "Advent I"},
		{date(2025, 12, 3), Advent, time.Wednesday, "Advent weekday"},
		{date(2025, 12, 24), Advent, time.Wednesday, "Christmas Eve — still Advent"},

		// Christmas
		{date(2025, 12, 25), Christmas, time.Thursday, "Christmas Day"},
		{date(2026, 1, 6), Christmas, time.Tuesday, "Epiphany feast — still Christmas season"},
		{date(2026, 1, 10), Christmas, time.Saturday, "Day before Baptism — Christmas"},

		// Epiphany
		{date(2026, 1, 11), Epiphany, time.Sunday, "Baptism of the Lord — Epiphany starts"},
		{date(2026, 1, 25), Epiphany, time.Sunday, "Third Sunday after Epiphany"},
		{date(2026, 2, 17), Epiphany, time.Tuesday, "Day before Ash Wednesday — Epiphany"},

		// Lent
		{date(2026, 2, 18), Lent, time.Wednesday, "Ash Wednesday"},
		{date(2026, 3, 8), Lent, time.Sunday, "Third Sunday in Lent"},
		{date(2026, 3, 28), Lent, time.Saturday, "Day before Palm Sunday — Lent"},

		// Passiontide
		{date(2026, 3, 29), Passiontide, time.Sunday, "Palm Sunday"},
		{date(2026, 4, 2), Passiontide, time.Thursday, "Maundy Thursday"},
		{date(2026, 4, 3), Passiontide, time.Friday, "Good Friday"},
		{date(2026, 4, 4), Passiontide, time.Saturday, "Holy Saturday"},

		// Easter
		{date(2026, 4, 5), Easter, time.Sunday, "Easter Day"},
		{date(2026, 5, 14), Easter, time.Thursday, "Ascension of the Lord"},
		{date(2026, 5, 23), Easter, time.Saturday, "Eve of Pentecost — Easter"},

		// Pentecost
		{date(2026, 5, 24), Pentecost, time.Sunday, "Day of Pentecost"},
		{date(2026, 5, 31), Pentecost, time.Sunday, "Trinity Sunday"},
		{date(2026, 7, 15), Pentecost, time.Wednesday, "Summer feria"},
		{date(2026, 10, 31), Pentecost, time.Saturday, "Eve of All Saints — still Pentecost"},

		// AllSaints
		{date(2026, 11, 1), AllSaints, time.Sunday, "All Saints' Day"},
		{date(2026, 11, 22), AllSaints, time.Sunday, "Reign of Christ"},
		{date(2026, 11, 28), AllSaints, time.Saturday, "Day before Advent II — AllSaints"},

		// Second Advent cycle
		{date(2026, 11, 29), Advent, time.Sunday, "Advent I (next year)"},
		{date(2026, 12, 5), Advent, time.Saturday, "Early second Advent feria"},

		// Christmas II — Dec 25 must not be Advent even though AdventII started Nov 29
		{date(2026, 12, 25), Christmas, time.Friday, "Christmas Day 2026"},
		{date(2026, 12, 28), Christmas, time.Monday, "Post-Christmas feria 2026"},
	}

	for _, tt := range tests {
		t.Run(tt.label, func(t *testing.T) {
			got, gotDOW := SeasonOf(tt.date, bounds2026)
			if got != tt.season {
				t.Errorf("SeasonOf(%s) = %s, want %s",
					tt.date.Format("2006-01-02"), got, tt.season)
			}
			if gotDOW != tt.dow {
				t.Errorf("SeasonOf(%s) weekday = %s, want %s",
					tt.date.Format("2006-01-02"), gotDOW, tt.dow)
			}
		})
	}
}

// TestFormSeasonOf covers the office-form season boundaries using fullBounds2026
// (all fields populated, mirroring data/season_bounds.json).
//
// These expected values must stay in sync with officeFormSeason() in web/app.js.
// If a season boundary is wrong here and correct in JS (or vice versa), the Go
// and web app will disagree on which office form to show.
func TestFormSeasonOf(t *testing.T) {
	tests := []struct {
		date   time.Time
		form   string
		label  string
	}{
		// Advent
		{date(2025, 11, 30), "Advent", "Advent I"},
		{date(2025, 12, 24), "Advent", "Christmas Eve — Advent form"},

		// Christmas
		{date(2025, 12, 25), "Christmas", "Christmas Day"},
		{date(2026, 1, 10), "Christmas", "Day before Baptism of the Lord"},

		// Epiphany form: Baptism of the Lord through day before Presentation
		{date(2026, 1, 11), "Epiphany", "Baptism of the Lord — Epiphany form starts"},
		{date(2026, 2, 1), "Epiphany", "Day before Presentation — still Epiphany form"},

		// Ordinary (post-Presentation, pre-Ash Wednesday)
		{date(2026, 2, 2), "OrdinaryTime", "Presentation — Epiphany form ends"},
		{date(2026, 2, 17), "OrdinaryTime", "Day before Ash Wednesday — Ordinary"},

		// Lent
		{date(2026, 2, 18), "Lent", "Ash Wednesday"},
		{date(2026, 3, 21), "Lent", "Day before Passiontide — Lent"},

		// Passiontide: 5th Sunday in Lent through Holy Saturday
		{date(2026, 3, 22), "Passiontide", "5th Sunday in Lent (Passion Sunday)"},
		{date(2026, 3, 29), "Passiontide", "Palm Sunday — still Passiontide form"},
		{date(2026, 4, 4), "Passiontide", "Holy Saturday"},

		// Easter: Easter Day through day before Ascension
		{date(2026, 4, 5), "Easter", "Easter Day"},
		{date(2026, 5, 13), "Easter", "Day before Ascension — Easter form"},

		// Pentecost form: Ascension through Trinity Sunday
		{date(2026, 5, 14), "Pentecost", "Ascension — Pentecost form starts"},
		{date(2026, 5, 24), "Pentecost", "Pentecost Sunday"},
		{date(2026, 5, 31), "Pentecost", "Trinity Sunday — last day of Pentecost form"},

		// Ordinary (post-Trinity)
		{date(2026, 6, 1), "OrdinaryTime", "Day after Trinity — Ordinary resumes"},
		{date(2026, 10, 31), "OrdinaryTime", "Eve of All Saints — Ordinary"},

		// AllSaints
		{date(2026, 11, 1), "AllSaints", "All Saints' Day"},
		{date(2026, 11, 28), "AllSaints", "Day before Advent II"},

		// Second Advent
		{date(2026, 11, 29), "Advent", "Advent I (year N+1)"},

		// Christmas II overrides Advent
		{date(2026, 12, 25), "Christmas", "Christmas Day 2026"},
	}

	for _, tt := range tests {
		t.Run(tt.label, func(t *testing.T) {
			got := FormSeasonOf(tt.date, fullBounds2026)
			if got != tt.form {
				t.Errorf("FormSeasonOf(%s) = %q, want %q",
					tt.date.Format("2006-01-02"), got, tt.form)
			}
		})
	}
}
