// Package lectionary provides a parsed Anglican BAS/PWC Daily Office lectionary.
// Given a date, Lookup returns a fully structured Day with readings metadata.
//
// Usage:
//
//	l, err := lectionary.Load()
//	day, err := l.Lookup(time.Now())
package lectionary

import (
	"embed"
	"encoding/json"
	"fmt"
	"strings"
	"time"
)

//go:embed data/season_bounds.json
var seasonBoundsData []byte

//go:embed data/lectionary
var lectionaryFS embed.FS

// Day is a fully resolved liturgical day from the BAS lectionary.
type Day struct {
	Date    time.Time
	Season  Season
	Weekday time.Weekday

	// Name is the primary liturgical name, e.g. "Ascension of the Lord".
	Name string
	// Rank is the liturgical rank extracted from the lectionary.
	Rank Rank
	// Colour is the liturgical colour string, e.g. "White or Gold".
	Colour string

	// Eucharist is the eucharistic propers for the day as a plain string,
	// e.g. "(Year A) Propers 268; Is 2:1-5; Ps 122; Rom 13:11-14; Mt 24:36-44".
	Eucharist string

	// Observances lists secondary liturgical labels for the day, e.g.
	// "fast_day", "eve_of:Christmas", "octave_of_easter", "canada_day".
	// Nil for days with no secondary observances.
	Observances []string

	Morning Office
	Evening Office

	// Notes holds supplementary liturgical data from the lectionary's extra
	// column: O Antiphons, precedence rules, pastoral notes, ember crossrefs, etc.
	// Nil for days with no supplementary data.
	Notes []Note
}

// Note is one supplementary annotation attached to a liturgical day.
type Note struct {
	// Type classifies the note content:
	// "o_antiphon", "precedence_rule", "pastoral", "ember_crossref",
	// "rogation_crossref", "civil_day", "week_of_prayer",
	// "office_note", "reconciliation_propers".
	Type string
	// Text is the full decoded note content.
	Text string
}

// Office holds the Daily Office readings for one time of day.
type Office struct {
	// Label is the named-observance prefix when multiple alternatives exist,
	// e.g. "Saint Stephen" or "Feria". Empty for single-option days.
	Label string

	// Psalms is the primary psalm set for this office.
	// When or-alternatives exist (PsalmSets is non-nil), Psalms holds the
	// main appointed set (the last group after "or").
	Psalms []Psalm

	// PsalmSets is populated when the lectionary lists psalm or-alternatives
	// (e.g. "[59, 60] or 19, 46"). The first group is the penitential/optional
	// alternative; the last group is the main appointed set (mirrored in Psalms).
	// Nil when there is only one psalm set.
	PsalmSets [][]Psalm

	// YearNote is "1" or "2" when the lectionary annotates a specific year
	// (e.g. Advent I, where the psalm set differs by BCP year). Empty otherwise.
	YearNote string

	Lessons []Lesson

	// LessonsPick is 0 for "read all lessons" and >0 when the lectionary says
	// "two of the following N readings" — indicating how many to choose.
	LessonsPick int

	// Collect is the BAS collect page reference string, e.g. "343" or
	// "270 or 395 (Ember)" when alternatives exist.
	Collect string

	// Note holds a cross-reference for non-standard entries, e.g.
	// "Common of a Martyr 432/3 or FAS 187" or "As Proper 9, except".
	Note string

	// Alternate is the secondary set of readings when the lectionary provides
	// multiple alternatives (feast vs. feria, different observances, etc.).
	// Nil when there is only one option.
	Alternate *Office
}

// Psalm is one psalm citation within an office.
type Psalm struct {
	// Citation is the psalm reference, e.g. "8", "119:1-24", "95 (Invitatory)".
	Citation string
	// Optional is true when the source encloses the citation in parentheses
	// or square brackets, indicating it may be omitted at the officiant's discretion.
	Optional bool
}

// Lesson is one scripture lesson within an office.
type Lesson struct {
	// Citation is the scripture reference, e.g. "Dan 7:9-14".
	Citation string
	// Optional is true when the source encloses the citation in parentheses.
	Optional bool
}

// Rank is the liturgical rank of a day.
type Rank int

const (
	Feria         Rank = iota // ordinary weekday
	Commemoration             // Com
	Memorial                  // Mem
	HolyDay                   // HD
	PrincipalFeast            // PF
)

func (r Rank) String() string {
	switch r {
	case PrincipalFeast:
		return "PF"
	case HolyDay:
		return "HD"
	case Memorial:
		return "Mem"
	case Commemoration:
		return "Com"
	default:
		return "Feria"
	}
}

// Lectionary holds the parsed calendar for one liturgical year.
type Lectionary struct {
	// Bounds exposes the computed season boundary dates for inspection or testing.
	Bounds SeasonBounds

	days map[string]*Day
}

// Load parses the embedded 2026 BAS lectionary JSON and returns a Lectionary
// ready for date lookups.
func Load() (*Lectionary, error) {
	var meta lectMeta
	if err := json.Unmarshal(seasonBoundsData, &meta); err != nil {
		return nil, fmt.Errorf("lectionary: parsing season bounds: %w", err)
	}

	bounds, err := boundsFromMeta(meta)
	if err != nil {
		return nil, fmt.Errorf("lectionary: season bounds: %w", err)
	}

	monthFiles, err := lectionaryFS.ReadDir("data/lectionary")
	if err != nil {
		return nil, fmt.Errorf("lectionary: reading embedded dir: %w", err)
	}

	l := &Lectionary{
		Bounds: bounds,
		days:   make(map[string]*Day, 400),
	}

	for _, mf := range monthFiles {
		data, err := lectionaryFS.ReadFile("data/lectionary/" + mf.Name())
		if err != nil {
			return nil, fmt.Errorf("lectionary: reading %s: %w", mf.Name(), err)
		}
		var month map[string]*lectEntry
		if err := json.Unmarshal(data, &month); err != nil {
			return nil, fmt.Errorf("lectionary: parsing %s: %w", mf.Name(), err)
		}
		for _, e := range month {
			d, err := time.Parse("2006-01-02", e.Date)
			if err != nil {
				continue
			}
			season, dow := SeasonOf(d, bounds)
			var notes []Note
			for _, n := range e.Notes {
				notes = append(notes, Note{Type: n.Type, Text: n.Text})
			}
			l.days[e.Date] = &Day{
				Date:        d,
				Season:      season,
				Weekday:     dow,
				Name:        e.Name,
				Rank:        rankFromString(e.Rank),
				Colour:      e.Colour,
				Eucharist:   e.Eucharist,
				Observances: e.Observances,
				Morning:     officeFromLect(e.Morning),
				Evening:     officeFromLect(e.Evening),
				Notes:       notes,
			}
		}
	}

	return l, nil
}

// Lookup returns the Day for the given date, or an error if the date is not
// covered by the lectionary.
func (l *Lectionary) Lookup(d time.Time) (*Day, error) {
	key := d.Format("2006-01-02")
	day, ok := l.days[key]
	if !ok {
		return nil, fmt.Errorf("lectionary: no entry for %s", key)
	}
	return day, nil
}

// AllDays returns every loaded Day in unspecified order.
func (l *Lectionary) AllDays() []*Day {
	out := make([]*Day, 0, len(l.days))
	for _, d := range l.days {
		out = append(out, d)
	}
	return out
}

// ── Internal JSON types ────────────────────────────────────────────────────────

type lectMeta struct {
	AdventI      string `json:"advent_i"`
	Christmas    string `json:"christmas"`
	Epiphany     string `json:"epiphany"`
	AshWednesday string `json:"ash_wednesday"`
	PalmSunday   string `json:"palm_sunday"`
	Easter       string `json:"easter"`
	Pentecost    string `json:"pentecost"`
	AllSaints    string `json:"all_saints"`
	AdventII     string `json:"advent_ii"`
	ChristmasII  string `json:"christmas_ii"` // optional; Christmas of year N+1
}

type lectEntry struct {
	Date        string      `json:"date"`
	Name        string      `json:"name"`
	Rank        string      `json:"rank"`
	Colour      string      `json:"colour"`
	Observances []string    `json:"observances"`
	Eucharist   string      `json:"eucharist"`
	Morning     lectOffice  `json:"morning"`
	Evening     lectOffice  `json:"evening"`
	Notes       []lectNote  `json:"notes"`
}

type lectNote struct {
	Type string `json:"type"`
	Text string `json:"text"`
}

type lectOffice struct {
	Label       string       `json:"label"`
	Psalms      []lectItem   `json:"psalms"`
	PsalmSets   [][]lectItem `json:"psalm_sets"`
	YearNote    string       `json:"year_note"`
	Lessons     []lectItem   `json:"lessons"`
	LessonsPick int          `json:"lessons_pick"`
	Collect     string       `json:"collect"`
	Note        string       `json:"note"`
	Alternate   *lectOffice  `json:"alternate"`
}

// lectItem unmarshals a YAML value that is either a plain string or a
// {citation: ..., optional: true} map. Plain strings wrapped in "(...)"
// are treated as optional.
type lectItem struct {
	Citation string
	Optional bool
}

func (item *lectItem) UnmarshalJSON(data []byte) error {
	// Struct form: {"citation": "...", "optional": true}
	var m struct {
		Citation string `json:"citation"`
		Optional bool   `json:"optional"`
	}
	if err := json.Unmarshal(data, &m); err == nil && m.Citation != "" {
		item.Citation = m.Citation
		item.Optional = m.Optional
		return nil
	}
	// Plain string form: "Gen 1:1" or "(Gen 1:1)" for optional
	var s string
	if err := json.Unmarshal(data, &s); err != nil {
		return fmt.Errorf("lectionary: cannot unmarshal item: %w", err)
	}
	if strings.HasPrefix(s, "(") && strings.HasSuffix(s, ")") {
		item.Citation = s[1 : len(s)-1]
		item.Optional = true
	} else {
		item.Citation = s
	}
	return nil
}

// ── Conversion helpers ─────────────────────────────────────────────────────────

func boundsFromMeta(m lectMeta) (SeasonBounds, error) {
	parse := func(s, name string) (time.Time, error) {
		if s == "" {
			return time.Time{}, fmt.Errorf("missing %s", name)
		}
		return time.Parse("2006-01-02", s)
	}
	var b SeasonBounds
	var err error
	if b.AdventI, err = parse(m.AdventI, "advent_i"); err != nil {
		return b, err
	}
	if b.Christmas, err = parse(m.Christmas, "christmas"); err != nil {
		return b, err
	}
	if b.Epiphany, err = parse(m.Epiphany, "epiphany"); err != nil {
		return b, err
	}
	if b.AshWednesday, err = parse(m.AshWednesday, "ash_wednesday"); err != nil {
		return b, err
	}
	if b.PalmSunday, err = parse(m.PalmSunday, "palm_sunday"); err != nil {
		return b, err
	}
	if b.Easter, err = parse(m.Easter, "easter"); err != nil {
		return b, err
	}
	if b.Pentecost, err = parse(m.Pentecost, "pentecost"); err != nil {
		return b, err
	}
	if b.AllSaints, err = parse(m.AllSaints, "all_saints"); err != nil {
		return b, err
	}
	if b.AdventII, err = parse(m.AdventII, "advent_ii"); err != nil {
		return b, err
	}
	if m.ChristmasII != "" {
		if b.ChristmasII, err = time.Parse("2006-01-02", m.ChristmasII); err != nil {
			return b, fmt.Errorf("christmas_ii: %w", err)
		}
	}
	return b, nil
}

func rankFromString(s string) Rank {
	switch s {
	case "principal_feast":
		return PrincipalFeast
	case "holy_day":
		return HolyDay
	case "memorial":
		return Memorial
	case "commemoration":
		return Commemoration
	default:
		return Feria
	}
}

func officeFromLect(o lectOffice) Office {
	off := Office{
		Label:       o.Label,
		YearNote:    o.YearNote,
		LessonsPick: o.LessonsPick,
		Collect:     o.Collect,
		Note:        o.Note,
	}

	if len(o.PsalmSets) > 0 {
		off.PsalmSets = make([][]Psalm, len(o.PsalmSets))
		for i, group := range o.PsalmSets {
			ps := make([]Psalm, len(group))
			for j, item := range group {
				ps[j] = Psalm{Citation: item.Citation, Optional: item.Optional}
			}
			off.PsalmSets[i] = ps
		}
		// Primary psalms = last group (the main appointed set, not the penitential alternative).
		off.Psalms = off.PsalmSets[len(off.PsalmSets)-1]
	} else {
		off.Psalms = make([]Psalm, len(o.Psalms))
		for i, item := range o.Psalms {
			off.Psalms[i] = Psalm{Citation: item.Citation, Optional: item.Optional}
		}
	}

	off.Lessons = make([]Lesson, len(o.Lessons))
	for i, item := range o.Lessons {
		off.Lessons[i] = Lesson{Citation: item.Citation, Optional: item.Optional}
	}

	if o.Alternate != nil {
		alt := officeFromLect(*o.Alternate)
		off.Alternate = &alt
	}

	return off
}
