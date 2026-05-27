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

	out := office.Render(day, "mp", ps, nil, nil, nil, l.Bounds)

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

	out := office.Render(day, "ep", ps, nil, nil, nil, l.Bounds)

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

	out := office.Render(day, "mp", nil, nil, nil, nil, l.Bounds)

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

	out := office.Render(day, "mp", ps, nil, nil, nil, l.Bounds)

	if out == "" {
		t.Error("expected non-empty output for ordinary day")
	}
	if strings.Contains(out, "o_antiphon") {
		t.Error("ordinary day should have no O Antiphon notes")
	}
}

// TestRenderOrdinaryFormAfterTrinity verifies that weekdays after Trinity Sunday
// use the ordinary weekday office forms (not pentecost-mp/ep).
// The ordinary Wednesday MP form includes an Invitatory; pentecost-mp does not.
func TestRenderOrdinaryFormAfterTrinity(t *testing.T) {
	l, ps := mustLoad(t)
	forms, err := lectionary.LoadForms()
	if err != nil {
		t.Fatalf("LoadForms: %v", err)
	}

	// 2026-06-10 is a Wednesday after Trinity Sunday (post-Pentecost ordinary time).
	day := mustLookup(t, l, 2026, 6, 10)
	if day.Season != lectionary.Pentecost {
		t.Fatalf("expected Pentecost (broad) season, got %s", day.Season)
	}

	out := office.Render(day, "mp", ps, nil, nil, forms, l.Bounds)

	// ordinary-wednesday-mp has an Invitatory; pentecost-mp does not.
	if !strings.Contains(out, "Invitatory Psalm") {
		t.Error("post-Trinity Wednesday: missing Invitatory Psalm (wrong form selected)")
	}
}

// TestRenderPentecostFormDuringAscensionPeriod verifies that the pentecost-mp/ep
// form is used from Ascension Day through Trinity Sunday (inclusive).
func TestRenderPentecostFormDuringAscensionPeriod(t *testing.T) {
	l, ps := mustLoad(t)
	forms, err := lectionary.LoadForms()
	if err != nil {
		t.Fatalf("LoadForms: %v", err)
	}

	// 2026-05-16 is a Saturday between Ascension (May 14) and Pentecost (May 24).
	day := mustLookup(t, l, 2026, 5, 16)
	out := office.Render(day, "mp", ps, nil, nil, forms, l.Bounds)

	// pentecost-mp uses the Pentecost responsory; ordinary forms do not.
	if !strings.Contains(out, "Come, Holy Spirit") {
		t.Error("Ascension-period day: missing Pentecost responsory (wrong form selected)")
	}
	// pentecost-mp has no Invitatory; ordinary forms do.
	if strings.Contains(out, "Invitatory Psalm") {
		t.Error("Ascension-period day: unexpected Invitatory Psalm (wrong form selected)")
	}
}

// TestRenderWithNote checks that O Antiphon notes appear in the output.
func TestRenderWithNote(t *testing.T) {
	l, ps := mustLoad(t)
	// Dec 17 has an O Antiphon note.
	day := mustLookup(t, l, 2025, 12, 17)

	out := office.Render(day, "mp", ps, nil, nil, nil, l.Bounds)

	if !strings.Contains(out, "O Sapientia") {
		t.Error("expected O Sapientia note in Dec 17 output")
	}
}

// TestRenderLessonsPick checks that the pick instruction appears when set.
func TestRenderLessonsPick(t *testing.T) {
	l, ps := mustLoad(t)
	// Christmas Eve morning: "Two of the following three readings".
	day := mustLookup(t, l, 2025, 12, 24)

	out := office.Render(day, "mp", ps, nil, nil, nil, l.Bounds)

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

	out := office.Render(day, "mp", ps, nil, nil, nil, l.Bounds)

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

	out := office.Render(day, "ep", ps, nil, nil, nil, l.Bounds)

	if !strings.Contains(out, "[59, 60] or 19, 46") {
		t.Errorf("expected psalm-sets display, got output missing '[59, 60] or 19, 46'")
	}
}

// ── Scripture integration (uses embedded KJV) ─────────────────────────────────

// TestRenderWithKJV verifies that actual scripture text appears in the rendered
// office when the embedded KJV bible is provided.
func TestRenderWithKJV(t *testing.T) {
	l, ps := mustLoad(t)
	collects, err := lectionary.LoadCollects()
	if err != nil {
		t.Fatalf("LoadCollects: %v", err)
	}
	// 2026-05-16: Num 11:16-17,24-29 and Eph 2:11-22 are appointed.
	day := mustLookup(t, l, 2026, 5, 16)
	out := office.Render(day, "mp", ps, lectionary.KJV(), collects, nil, l.Bounds)

	checks := []struct {
		label string
		want  string
	}{
		{"KJV Numbers text", "Gather unto me seventy men"},
		{"KJV Ephesians text", "far off"},
		{"attribution", "Translation: KJV"},
	}
	for _, c := range checks {
		if !strings.Contains(out, c.want) {
			t.Errorf("%s: output missing %q", c.label, c.want)
		}
	}
	// Local bible must NOT produce an api.bible link.
	if strings.Contains(out, "api.bible") {
		t.Error("local KJV should not produce an api.bible attribution link")
	}
}

// TestRenderKJVApocrypha verifies that deuterocanonical lessons render
// with actual text when the embedded KJV is provided.
func TestRenderKJVApocrypha(t *testing.T) {
	l, ps := mustLoad(t)
	// 2026-11-01 (All Saints): morning lesson is 2 Esd 2:42-47.
	day := mustLookup(t, l, 2026, 11, 1)
	out := office.Render(day, "mp", ps, lectionary.KJV(), nil, nil, l.Bounds)

	if !strings.Contains(out, "2 Esd 2:42-47") {
		t.Error("missing 2 Esdras citation")
	}
	if !strings.Contains(out, "I Esdras saw") {
		t.Error("missing 2 Esdras text — apocryphal lesson not rendered")
	}
}

// TestRenderKJVNoCitationOnlyFallback verifies that when KJV has no data for a
// citation (empty string from Lookup) the renderer still shows the citation heading.
func TestRenderKJVCitationHeadingAlwaysShown(t *testing.T) {
	l, ps := mustLoad(t)
	day := mustLookup(t, l, 2026, 5, 16)
	// Render without any bible — citation headings must still appear.
	out := office.Render(day, "mp", ps, nil, nil, nil, l.Bounds)

	if !strings.Contains(out, "### The Reading: Num 11:16-17, 24-29") {
		t.Error("lesson citation heading missing when no bible provided")
	}
}

// TestRenderYearNote checks that the Year annotation appears next to the psalm heading.
func TestRenderYearNote(t *testing.T) {
	l, ps := mustLoad(t)
	// Advent I 2025 morning: Year 2 annotation.
	day := mustLookup(t, l, 2025, 11, 30)

	out := office.Render(day, "mp", ps, nil, nil, nil, l.Bounds)

	if !strings.Contains(out, "(Year 2)") {
		t.Error("expected '(Year 2)' in Advent I output")
	}
}
