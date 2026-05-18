package lectionary

import (
	"strings"
	"testing"
)

func mustLoadCollects(t *testing.T) *Collects {
	t.Helper()
	c, err := LoadCollects()
	if err != nil {
		t.Fatalf("LoadCollects: %v", err)
	}
	return c
}

func TestCollectsLoad(t *testing.T) {
	c := mustLoadCollects(t)
	if len(c.data) == 0 {
		t.Fatal("no collects loaded")
	}
}

func TestCollectsLookupSimple(t *testing.T) {
	c := mustLoadCollects(t)
	// Advent I collect — "armour of light"
	col := c.Lookup("268")
	if col == nil {
		t.Fatal("Lookup(268): got nil")
	}
	if !strings.Contains(col.Text, "armour of light") {
		t.Errorf("Lookup(268): expected 'armour of light' in text, got: %q", col.Text[:min(80, len(col.Text))])
	}
	if col.Name != "First Sunday of Advent" {
		t.Errorf("Lookup(268): expected name 'First Sunday of Advent', got %q", col.Name)
	}
}

func TestCollectsLookupCompound(t *testing.T) {
	c := mustLoadCollects(t)
	// Compound ref — primary page extracted, parenthetical ignored.
	col := c.Lookup("268 (Com: 434 or FAS 361)")
	if col == nil {
		t.Fatal("Lookup with compound ref: got nil")
	}
	if !strings.Contains(col.Text, "armour of light") {
		t.Errorf("Lookup compound: expected Advent I collect, got: %q", col.Text[:min(80, len(col.Text))])
	}
}

func TestCollectsLookupOrAlternative(t *testing.T) {
	c := mustLoadCollects(t)
	// "270 or 395 (Ember)" — should use page 270.
	col := c.Lookup("270 or 395 (Ember)")
	if col == nil {
		t.Fatal("Lookup or-alternative: got nil")
	}
}

func TestCollectsLookupAshWednesday(t *testing.T) {
	c := mustLoadCollects(t)
	col := c.Lookup("281")
	if col == nil {
		t.Fatal("Lookup(281): got nil")
	}
	if !strings.Contains(col.Text, "contrite hearts") {
		t.Errorf("Lookup(281): expected Ash Wednesday collect, got: %q", col.Text[:min(80, len(col.Text))])
	}
	if col.Name != "Ash Wednesday" {
		t.Errorf("Lookup(281): expected name 'Ash Wednesday', got %q", col.Name)
	}
}

func TestCollectsLookupMissing(t *testing.T) {
	c := mustLoadCollects(t)
	// Truly absent page reference.
	if got := c.Lookup("999"); got != nil {
		t.Errorf("Lookup(999): expected nil for absent page, got non-nil")
	}
	if got := c.Lookup(""); got != nil {
		t.Errorf("Lookup empty ref: expected nil")
	}
}

func TestCollectsMetadata(t *testing.T) {
	c := mustLoadCollects(t)
	cases := []struct {
		page    string
		section string
		season  string
		proper  int
		date    string
	}{
		{"268", "Sundays and Holy Days", "Advent", 0, ""},
		{"343", "Sundays and Holy Days", "Easter", 0, ""},
		{"360", "Sundays and Holy Days", "OrdinaryTime", 10, ""},
		{"394", "Sundays and Holy Days", "OrdinaryTime", 0, ""},
		{"407", "Saints' Days and Other Holy Days", "", 0, "14 May"},
		{"432", "Common Propers", "", 0, ""},
	}
	for _, tc := range cases {
		col := c.Lookup(tc.page)
		if col == nil {
			t.Errorf("p.%s: got nil", tc.page)
			continue
		}
		if col.Section != tc.section {
			t.Errorf("p.%s: Section=%q want %q", tc.page, col.Section, tc.section)
		}
		if col.Season != tc.season {
			t.Errorf("p.%s: Season=%q want %q", tc.page, col.Season, tc.season)
		}
		if col.Proper != tc.proper {
			t.Errorf("p.%s: Proper=%d want %d", tc.page, col.Proper, tc.proper)
		}
		if col.Date != tc.date {
			t.Errorf("p.%s: Date=%q want %q", tc.page, col.Date, tc.date)
		}
	}
}

func TestCollectsHasName(t *testing.T) {
	c := mustLoadCollects(t)
	// Spot-check that key feasts have names.
	cases := []struct {
		page string
		want string
	}{
		{"280", "The Epiphany"},
		{"299", "The Sunday of the Passion"},
		{"308", "Good Friday"},
		{"335", "Easter"},
		{"343", "Ascension of the Lord"},
		{"345", "The Day of Pentecost"},
		{"410", "The Birth of Saint John the Baptist"},
	}
	for _, tc := range cases {
		col := c.Lookup(tc.page)
		if col == nil {
			t.Errorf("p.%s: got nil", tc.page)
			continue
		}
		if !strings.Contains(col.Name, tc.want) {
			t.Errorf("p.%s: name %q does not contain %q", tc.page, col.Name, tc.want)
		}
	}
}
