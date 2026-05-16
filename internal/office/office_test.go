package office_test

import (
	"strings"
	"testing"
	"time"

	lectionary "github.com/astaticvoid/pwc-office"
	"github.com/astaticvoid/pwc-office/internal/office"
)

func mustLoad(t *testing.T) (*lectionary.Lectionary, *lectionary.Psalter) {
	t.Helper()
	l, err := lectionary.Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	ps, err := lectionary.LoadPsalter()
	if err != nil {
		t.Fatalf("LoadPsalter: %v", err)
	}
	return l, ps
}

func mustLookup(t *testing.T, l *lectionary.Lectionary, y, m, d int) *lectionary.Day {
	t.Helper()
	day, err := l.Lookup(time.Date(y, time.Month(m), d, 0, 0, 0, 0, time.UTC))
	if err != nil {
		t.Fatalf("Lookup %04d-%02d-%02d: %v", y, m, d, err)
	}
	return day
}

// TestRenderAscensionMP checks that the Ascension morning office contains the
// expected day name, psalm text, lesson citations, and collect reference.
func TestRenderAscensionMP(t *testing.T) {
	l, ps := mustLoad(t)
	day := mustLookup(t, l, 2026, 5, 14)

	out := office.Render(day, "mp", ps, nil, nil, nil)

	checks := []struct {
		label string
		want  string
	}{
		{"day name", "Ascension of the Lord"},
		{"season", "Easter"},
		{"rank", "PF"},
		{"colour", "White or Gold"},
		{"psalm 8 heading", "8"},
		{"psalm 8 text", "O Lord our governor"},
		{"psalm 47 text", "Clap your hands"},
		{"lesson 1", "Dan 7:9-14"},
		{"lesson 2", "Heb 2:5-18"},
		{"collect", "343"},
	}
	for _, c := range checks {
		if !strings.Contains(out, c.want) {
			t.Errorf("%s: output missing %q", c.label, c.want)
		}
	}
}

// TestRenderAscensionEP checks the evening office for the same day.
func TestRenderAscensionEP(t *testing.T) {
	l, ps := mustLoad(t)
	day := mustLookup(t, l, 2026, 5, 14)

	out := office.Render(day, "ep", ps, nil, nil, nil)

	if !strings.Contains(out, "Evening Prayer") {
		t.Error("missing 'Evening Prayer' in header")
	}
	if !strings.Contains(out, "Ezek 1:1-14") {
		t.Error("missing evening lesson citation")
	}
	if !strings.Contains(out, "Mt 28:16-20") {
		t.Error("missing evening lesson 2 citation")
	}
}

// TestRenderNilPsalter verifies that Render does not panic when no psalter
// is provided and produces no psalm text.
func TestRenderNilPsalter(t *testing.T) {
	l, _ := mustLoad(t)
	day := mustLookup(t, l, 2026, 5, 14)

	out := office.Render(day, "mp", nil, nil, nil, nil)

	if !strings.Contains(out, "Ascension of the Lord") {
		t.Error("missing day name without psalter")
	}
	// Without a psalter, psalm text should not appear.
	if strings.Contains(out, "O Lord our governor") {
		t.Error("psalm text should not appear without a psalter")
	}
}

// TestRenderOrdinaryDay checks a ferial day with no special observances.
func TestRenderOrdinaryDay(t *testing.T) {
	l, ps := mustLoad(t)
	day := mustLookup(t, l, 2026, 7, 8)

	out := office.Render(day, "mp", ps, nil, nil, nil)

	if out == "" {
		t.Error("expected non-empty output for ordinary day")
	}
	if strings.Contains(out, "o_antiphon") {
		t.Error("ordinary day should have no O Antiphon notes")
	}
}

// TestRenderOrdinaryTimeFormUsedInPentecostSeason verifies that weekdays in
// the Pentecost season use the ordinary weekday office forms (not pentecost-mp/ep).
// The ordinary Wednesday MP form includes an Invitatory; pentecost-mp does not.
func TestRenderOrdinaryTimeFormUsedInPentecostSeason(t *testing.T) {
	l, ps := mustLoad(t)
	forms, err := lectionary.LoadForms()
	if err != nil {
		t.Fatalf("LoadForms: %v", err)
	}

	// 2026-06-10 is a Wednesday in the Pentecost season (Feria rank).
	day := mustLookup(t, l, 2026, 6, 10)
	if day.Season != lectionary.Pentecost {
		t.Fatalf("expected Pentecost season, got %s", day.Season)
	}

	out := office.Render(day, "mp", ps, nil, nil, forms)

	// The ordinary-wednesday-mp form includes an Invitatory section.
	// If the wrong form (pentecost-mp) were used, this heading would be absent.
	if !strings.Contains(out, "Invitatory Psalm") {
		t.Error("ordinary Wednesday in Pentecost season: missing Invitatory Psalm (wrong form selected)")
	}
}

// TestRenderWithNote checks that O Antiphon notes appear in the output.
func TestRenderWithNote(t *testing.T) {
	l, ps := mustLoad(t)
	// Dec 17 has an O Antiphon note.
	day := mustLookup(t, l, 2025, 12, 17)

	out := office.Render(day, "mp", ps, nil, nil, nil)

	if !strings.Contains(out, "O Sapientia") {
		t.Error("expected O Sapientia note in Dec 17 output")
	}
}

// TestRenderLessonsPick checks that the pick instruction appears when set.
func TestRenderLessonsPick(t *testing.T) {
	l, ps := mustLoad(t)
	// Christmas Eve morning: "Two of the following three readings".
	day := mustLookup(t, l, 2025, 12, 24)

	out := office.Render(day, "mp", ps, nil, nil, nil)

	if !strings.Contains(out, "Two of the following") {
		t.Error("expected LessonsPick instruction for Christmas Eve")
	}
}

// TestRenderAlternate checks that both the primary and alternate office
// appear when the lectionary offers a feast-vs-feria choice.
func TestRenderAlternate(t *testing.T) {
	l, ps := mustLoad(t)
	// Dec 26: Saint Stephen (primary) or Feria (alternate).
	day := mustLookup(t, l, 2025, 12, 26)

	out := office.Render(day, "mp", ps, nil, nil, nil)

	for _, want := range []string{
		"Saint Stephen",
		"2 Chr 24:17-22",
		"Feria",
		"Is 41:8-10",
	} {
		if !strings.Contains(out, want) {
			t.Errorf("missing %q in alternate-office output", want)
		}
	}
}

// TestRenderPsalmSets checks that or-alternative psalm sets are shown.
func TestRenderPsalmSets(t *testing.T) {
	l, ps := mustLoad(t)
	// Feb 26 evening: [59, 60] or 19, 46.
	day := mustLookup(t, l, 2026, 2, 26)

	out := office.Render(day, "ep", ps, nil, nil, nil)

	if !strings.Contains(out, "[59, 60] or 19, 46") {
		t.Errorf("expected psalm-sets display, got output missing '[59, 60] or 19, 46'")
	}
}

// TestRenderYearNote checks that the Year annotation appears next to the psalm heading.
func TestRenderYearNote(t *testing.T) {
	l, ps := mustLoad(t)
	// Advent I 2025 morning: Year 2 annotation.
	day := mustLookup(t, l, 2025, 11, 30)

	out := office.Render(day, "mp", ps, nil, nil, nil)

	if !strings.Contains(out, "(Year 2)") {
		t.Error("expected '(Year 2)' in Advent I output")
	}
}
