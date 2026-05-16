package lectionary

import (
	"strings"
	"testing"
	"time"
)

// ── Season bounds (integration: uses embedded YAML) ───────────────────────────

func TestSeasonBounds(t *testing.T) {
	l, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	b := l.Bounds

	check := func(name string, got, want time.Time) {
		t.Helper()
		if !got.Equal(want) {
			t.Errorf("%s: got %s, want %s",
				name, got.Format("2006-01-02"), want.Format("2006-01-02"))
		}
	}
	check("AdventI", b.AdventI, date(2025, 11, 30))
	check("Christmas", b.Christmas, date(2025, 12, 25))
	check("Epiphany", b.Epiphany, date(2026, 1, 11))
	check("AshWednesday", b.AshWednesday, date(2026, 2, 18))
	check("PalmSunday", b.PalmSunday, date(2026, 3, 29))
	check("Easter", b.Easter, date(2026, 4, 5))
	check("Pentecost", b.Pentecost, date(2026, 5, 24))
	check("AllSaints", b.AllSaints, date(2026, 11, 1))
	check("AdventII", b.AdventII, date(2026, 11, 29))
}

// ── Lookup + parsed fields ─────────────────────────────────────────────────────

func TestLookupAscension(t *testing.T) {
	l, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	day, err := l.Lookup(date(2026, 5, 14))
	if err != nil {
		t.Fatalf("Lookup: %v", err)
	}

	if day.Season != Easter {
		t.Errorf("season: got %s, want Easter", day.Season)
	}
	if day.Rank != PrincipalFeast {
		t.Errorf("rank: got %s, want PF", day.Rank)
	}
	if day.Colour != "White or Gold" {
		t.Errorf("colour: got %q", day.Colour)
	}
	if day.Name != "Ascension of the Lord" {
		t.Errorf("name: got %q", day.Name)
	}

	// Morning: Ps 8, 47; Dan 7:9-14; Heb 2:5-18; Coll 343
	mp := day.Morning
	if len(mp.Psalms) != 2 {
		t.Fatalf("morning psalms count: got %d, want 2", len(mp.Psalms))
	}
	if mp.Psalms[0].Citation != "8" || mp.Psalms[1].Citation != "47" {
		t.Errorf("morning psalm citations: %+v", mp.Psalms)
	}
	if len(mp.Lessons) != 2 {
		t.Fatalf("morning lessons count: got %d, want 2", len(mp.Lessons))
	}
	if mp.Lessons[0].Citation != "Dan 7:9-14" {
		t.Errorf("morning lesson1: got %q", mp.Lessons[0].Citation)
	}
	if mp.Lessons[1].Citation != "Heb 2:5-18" {
		t.Errorf("morning lesson2: got %q", mp.Lessons[1].Citation)
	}
	if mp.Collect != "343" {
		t.Errorf("morning collect: got %q, want 343", mp.Collect)
	}
	if mp.Alternate != nil {
		t.Error("morning should have no alternate")
	}

	// Evening: Ps 24, 96; (Ezek 1:1-14, 24-28b); Mt 28:16-20; Coll 343
	ep := day.Evening
	if len(ep.Psalms) != 2 {
		t.Fatalf("evening psalms count: got %d, want 2", len(ep.Psalms))
	}
	if ep.Lessons[0].Optional != true {
		t.Errorf("evening lesson1 should be optional (parenthetical)")
	}
	if ep.Lessons[0].Citation != "Ezek 1:1-14, 24-28b" {
		t.Errorf("evening lesson1 citation: got %q", ep.Lessons[0].Citation)
	}
	if ep.Collect != "343" {
		t.Errorf("evening collect: got %q", ep.Collect)
	}
}

func TestLookupAlternates(t *testing.T) {
	l, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	// Dec 26 has Saint Stephen (HD) OR Feria alternatives.
	day, err := l.Lookup(date(2025, 12, 26))
	if err != nil {
		t.Fatalf("Lookup: %v", err)
	}

	mp := day.Morning
	if mp.Alternate == nil {
		t.Fatal("expected an alternate for Dec 26 morning")
	}
	if mp.Label == "" {
		t.Error("primary office should have a label (e.g. 'Saint Stephen')")
	}
	if mp.Alternate.Label == "" {
		t.Error("alternate office should have a label (e.g. 'Feria')")
	}
}

func TestLookupPsalmSets(t *testing.T) {
	l, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	// Feb 26, 2026 evening: "Ps [59, 60] or 19, 46" — psalm or-alternatives.
	day, err := l.Lookup(date(2026, 2, 26))
	if err != nil {
		t.Fatalf("Lookup: %v", err)
	}

	ep := day.Evening
	if len(ep.PsalmSets) != 2 {
		t.Fatalf("evening psalm_sets count: got %d, want 2", len(ep.PsalmSets))
	}
	// First set: penitential alternative [59, 60] — both optional
	if len(ep.PsalmSets[0]) != 2 {
		t.Fatalf("penitential set length: got %d, want 2", len(ep.PsalmSets[0]))
	}
	if ep.PsalmSets[0][0].Citation != "59" || !ep.PsalmSets[0][0].Optional {
		t.Errorf("penitential[0]: got %+v", ep.PsalmSets[0][0])
	}
	if ep.PsalmSets[0][1].Citation != "60" || !ep.PsalmSets[0][1].Optional {
		t.Errorf("penitential[1]: got %+v", ep.PsalmSets[0][1])
	}
	// Second set: main appointed [19, 46] — not optional
	if len(ep.PsalmSets[1]) != 2 {
		t.Fatalf("main set length: got %d, want 2", len(ep.PsalmSets[1]))
	}
	if ep.PsalmSets[1][0].Citation != "19" || ep.PsalmSets[1][0].Optional {
		t.Errorf("main[0]: got %+v", ep.PsalmSets[1][0])
	}
	// Psalms field mirrors the main (last) set
	if len(ep.Psalms) != 2 || ep.Psalms[0].Citation != "19" {
		t.Errorf("Psalms should mirror main set: got %+v", ep.Psalms)
	}
}

func TestLookupYearNote(t *testing.T) {
	l, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	// Advent I 2025: morning psalms annotated "(Year 2)"
	day, err := l.Lookup(date(2025, 11, 30))
	if err != nil {
		t.Fatalf("Lookup: %v", err)
	}
	if day.Morning.YearNote != "2" {
		t.Errorf("YearNote: got %q, want 2", day.Morning.YearNote)
	}
	if len(day.Morning.Psalms) == 0 {
		t.Error("expected morning psalms to be present")
	}
}

func TestLookupLessonsPick(t *testing.T) {
	l, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	// Christmas Eve morning: "Two of the following three readings:"
	day, err := l.Lookup(date(2025, 12, 24))
	if err != nil {
		t.Fatalf("Lookup: %v", err)
	}
	if day.Morning.LessonsPick != 2 {
		t.Errorf("LessonsPick: got %d, want 2", day.Morning.LessonsPick)
	}
	if len(day.Morning.Lessons) != 3 {
		t.Errorf("lesson count: got %d, want 3", len(day.Morning.Lessons))
	}
}

func TestLookupEucharist(t *testing.T) {
	l, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	// Advent I has a year annotation in the eucharist field.
	day, err := l.Lookup(date(2025, 11, 30))
	if err != nil {
		t.Fatalf("Lookup: %v", err)
	}
	if day.Eucharist == "" {
		t.Error("Eucharist should be non-empty")
	}
	if !strings.Contains(day.Eucharist, "Propers") {
		t.Errorf("Eucharist unexpected content: %q", day.Eucharist)
	}
}

func TestLookupObservances(t *testing.T) {
	l, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}

	// Christmas Eve: eve_of:Christmas
	day, err := l.Lookup(date(2025, 12, 24))
	if err != nil {
		t.Fatalf("Lookup: %v", err)
	}
	if len(day.Observances) == 0 {
		t.Fatal("expected observances on Christmas Eve")
	}
	found := false
	for _, o := range day.Observances {
		if o == "eve_of:Christmas" {
			found = true
		}
	}
	if !found {
		t.Errorf("observances: missing eve_of:Christmas, got %v", day.Observances)
	}

	// Ordinary feria: no observances.
	day2, err := l.Lookup(date(2026, 7, 8))
	if err != nil {
		t.Fatalf("Lookup: %v", err)
	}
	if len(day2.Observances) != 0 {
		t.Errorf("expected no observances on 2026-07-08, got %v", day2.Observances)
	}
}

func TestLookupNotes(t *testing.T) {
	l, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}

	// Dec 17 has an O Antiphon note.
	day, err := l.Lookup(date(2025, 12, 17))
	if err != nil {
		t.Fatalf("Lookup: %v", err)
	}
	if len(day.Notes) != 1 {
		t.Fatalf("notes count: got %d, want 1", len(day.Notes))
	}
	if day.Notes[0].Type != "o_antiphon" {
		t.Errorf("note type: got %q, want o_antiphon", day.Notes[0].Type)
	}
	if !strings.Contains(day.Notes[0].Text, "O Sapientia") {
		t.Errorf("note text missing O Sapientia: %q", day.Notes[0].Text)
	}

	// Ordinary day: no notes.
	day2, err := l.Lookup(date(2026, 7, 8))
	if err != nil {
		t.Fatalf("Lookup: %v", err)
	}
	if len(day2.Notes) != 0 {
		t.Errorf("expected no notes on 2026-07-08, got %v", day2.Notes)
	}
}
