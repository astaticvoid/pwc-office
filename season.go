package lectionary

import "time"

// Season represents a liturgical season.
type Season int

const (
	Advent       Season = iota
	Christmas           // Christmas Day through day before Baptism of the Lord
	Epiphany            // Baptism of the Lord through day before Ash Wednesday
	Lent                // Ash Wednesday through day before Palm Sunday
	Passiontide         // Palm Sunday through Holy Saturday
	Easter              // Easter Day through day before Pentecost
	Pentecost           // Pentecost Sunday through day before All Saints' Day
	AllSaints           // All Saints' Day through day before next Advent I
	OrdinaryTime        // fallback; not expected within the 2026 CSV range
)

func (s Season) String() string {
	switch s {
	case Advent:
		return "Advent"
	case Christmas:
		return "Christmas"
	case Epiphany:
		return "Epiphany"
	case Lent:
		return "Lent"
	case Passiontide:
		return "Passiontide"
	case Easter:
		return "Easter"
	case Pentecost:
		return "Pentecost"
	case AllSaints:
		return "AllSaints"
	default:
		return "OrdinaryTime"
	}
}

// SeasonBounds holds the first date of each season boundary for a liturgical year.
type SeasonBounds struct {
	AdventI      time.Time // First Sunday of Advent (year N)
	Christmas    time.Time // Christmas Day (year N)
	Epiphany     time.Time // Baptism of the Lord (season start)
	AshWednesday time.Time
	PalmSunday   time.Time
	Easter       time.Time
	Pentecost    time.Time
	AllSaints    time.Time // Nov 1
	AdventII     time.Time // First Sunday of Advent (year N+1)
	ChristmasII  time.Time // Christmas Day (year N+1); optional, resolves Dec 25 in Advent
}

// SeasonOf returns the liturgical season for date d, plus d's weekday.
// The weekday is always returned so callers can use it for per-weekday
// template selection in seasons like OrdinaryTime.
func SeasonOf(d time.Time, b SeasonBounds) (Season, time.Weekday) {
	d = midnight(d)
	dow := d.Weekday()
	switch {
	case !b.ChristmasII.IsZero() && !d.Before(b.ChristmasII):
		return Christmas, dow
	case !b.AdventII.IsZero() && !d.Before(b.AdventII):
		return Advent, dow
	case !b.AllSaints.IsZero() && !d.Before(b.AllSaints):
		return AllSaints, dow
	case !b.Pentecost.IsZero() && !d.Before(b.Pentecost):
		return Pentecost, dow
	case !b.Easter.IsZero() && !d.Before(b.Easter):
		return Easter, dow
	case !b.PalmSunday.IsZero() && !d.Before(b.PalmSunday):
		return Passiontide, dow
	case !b.AshWednesday.IsZero() && !d.Before(b.AshWednesday):
		return Lent, dow
	case !b.Epiphany.IsZero() && !d.Before(b.Epiphany):
		return Epiphany, dow
	case !b.Christmas.IsZero() && !d.Before(b.Christmas):
		return Christmas, dow
	case !b.AdventI.IsZero() && !d.Before(b.AdventI):
		return Advent, dow
	default:
		return OrdinaryTime, dow
	}
}

func midnight(t time.Time) time.Time {
	return time.Date(t.Year(), t.Month(), t.Day(), 0, 0, 0, 0, time.UTC)
}
