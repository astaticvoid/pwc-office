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
	Presentation time.Time // Candlemas, Feb 2 — Epiphany form ends here
	AshWednesday time.Time
	Passiontide  time.Time // Fifth Sunday in Lent (Passion Sunday) — Passiontide form starts
	PalmSunday   time.Time // fallback if Passiontide not set
	Easter       time.Time
	Ascension    time.Time // Ascension Day — Pentecost form starts
	Pentecost    time.Time // Pentecost Sunday — fallback if Ascension not set
	TrinityS     time.Time // Trinity Sunday — Pentecost form ends (ordinary resumes next day)
	AllSaints    time.Time // Nov 1
	AdventII     time.Time // First Sunday of Advent (year N+1)
	ChristmasII  time.Time // Christmas Day (year N+1); optional, resolves Dec 25 in Advent
}

// SeasonOf returns the broad liturgical season for date d (used for theming).
// Passiontide begins at the 5th Sunday in Lent if set, otherwise Palm Sunday.
// Pentecost season begins at Pentecost Sunday (not Ascension — see FormSeasonOf).
func SeasonOf(d time.Time, b SeasonBounds) (Season, time.Weekday) {
	d = midnight(d)
	dow := d.Weekday()

	passionStart := b.PalmSunday
	if !b.Passiontide.IsZero() {
		passionStart = b.Passiontide
	}

	switch {
	case !b.ChristmasII.IsZero() && !d.Before(b.ChristmasII):
		return Christmas, dow
	case !b.AdventII.IsZero() && !d.Before(b.AdventII):
		return Advent, dow
	case !b.AllSaints.IsZero() && !d.Before(b.AllSaints):
		return AllSaints, dow
	case !b.TrinityS.IsZero() && d.After(b.TrinityS):
		return OrdinaryTime, dow
	case !b.Pentecost.IsZero() && !d.Before(b.Pentecost):
		return Pentecost, dow
	case !b.Easter.IsZero() && !d.Before(b.Easter):
		return Easter, dow
	case !passionStart.IsZero() && !d.Before(passionStart):
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

// FormSeasonOf returns the season string used for office form lookup.
// This is more granular than SeasonOf: it distinguishes the post-Trinity
// ordinary period from the Pentecost season, and the post-Presentation
// ordinary period from Epiphany.
func FormSeasonOf(d time.Time, b SeasonBounds) string {
	d = midnight(d)

	passionStart := b.PalmSunday
	if !b.Passiontide.IsZero() {
		passionStart = b.Passiontide
	}
	pentecostFormStart := b.Pentecost
	if !b.Ascension.IsZero() {
		pentecostFormStart = b.Ascension
	}

	switch {
	case !b.ChristmasII.IsZero() && !d.Before(b.ChristmasII):
		return "Christmas"
	case !b.AdventII.IsZero() && !d.Before(b.AdventII):
		return "Advent"
	case !b.AllSaints.IsZero() && !d.Before(b.AllSaints):
		return "AllSaints"
	// Post-Trinity: ordinary weekday forms (Trinity Sunday is the last day of Pentecost form)
	case !b.TrinityS.IsZero() && d.After(b.TrinityS):
		return "OrdinaryTime"
	case !pentecostFormStart.IsZero() && !d.Before(pentecostFormStart):
		return "Pentecost"
	case !b.Easter.IsZero() && !d.Before(b.Easter):
		return "Easter"
	case !passionStart.IsZero() && !d.Before(passionStart):
		return "Passiontide"
	case !b.AshWednesday.IsZero() && !d.Before(b.AshWednesday):
		return "Lent"
	// Post-Presentation: ordinary weekday forms until Ash Wednesday
	case !b.Presentation.IsZero() && !d.Before(b.Presentation):
		return "OrdinaryTime"
	case !b.Epiphany.IsZero() && !d.Before(b.Epiphany):
		return "Epiphany"
	case !b.Christmas.IsZero() && !d.Before(b.Christmas):
		return "Christmas"
	case !b.AdventI.IsZero() && !d.Before(b.AdventI):
		return "Advent"
	default:
		return "OrdinaryTime"
	}
}

func midnight(t time.Time) time.Time {
	return time.Date(t.Year(), t.Month(), t.Day(), 0, 0, 0, 0, time.UTC)
}
