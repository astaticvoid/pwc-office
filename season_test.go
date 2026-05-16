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
