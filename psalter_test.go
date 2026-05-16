package lectionary

import (
	"strings"
	"testing"
)

func TestLoadPsalter(t *testing.T) {
	ps, err := LoadPsalter()
	if err != nil {
		t.Fatalf("LoadPsalter: %v", err)
	}
	if ps == nil {
		t.Fatal("got nil Psalter")
	}
	if len(ps.psalms) != 150 {
		t.Errorf("psalm count: got %d, want 150", len(ps.psalms))
	}
}

func TestPsalterBookField(t *testing.T) {
	ps, err := LoadPsalter()
	if err != nil {
		t.Fatalf("LoadPsalter: %v", err)
	}
	cases := []struct{ num, book int }{
		{1, 1}, {41, 1},
		{42, 2}, {72, 2},
		{73, 3}, {89, 3},
		{90, 4}, {106, 4},
		{107, 5}, {150, 5},
	}
	for _, c := range cases {
		e, ok := ps.psalms[c.num]
		if !ok {
			t.Errorf("psalm %d not found", c.num)
			continue
		}
		if e.Book != c.book {
			t.Errorf("psalm %d: book = %d, want %d", c.num, e.Book, c.book)
		}
	}
}

func TestPsalterLookupFull(t *testing.T) {
	ps, err := LoadPsalter()
	if err != nil {
		t.Fatalf("LoadPsalter: %v", err)
	}
	text := ps.Lookup("8")
	if text == "" {
		t.Fatal("Lookup(8): got empty string")
	}
	if !strings.HasPrefix(text, "1 ") {
		t.Errorf("Lookup(8): expected text to start with verse 1, got: %q", text[:min(40, len(text))])
	}
	// Full psalm should contain multiple verses.
	if !strings.Contains(text, "9 ") {
		t.Errorf("Lookup(8): expected verse 9 in full psalm")
	}
}

func TestPsalterLookupVerseRange(t *testing.T) {
	ps, err := LoadPsalter()
	if err != nil {
		t.Fatalf("LoadPsalter: %v", err)
	}
	text := ps.Lookup("119:1-24")
	if text == "" {
		t.Fatal("Lookup(119:1-24): got empty string")
	}
	// May start with a section header (e.g. "Aleph") before verse 1.
	if !strings.Contains(text, "\n1 ") && !strings.HasPrefix(text, "1 ") {
		t.Errorf("expected verse 1 in range result, got: %q", text[:min(60, len(text))])
	}
	// Verse 25 should not appear as a verse line.
	for _, line := range strings.Split(text, "\n") {
		if strings.HasPrefix(line, "25 ") {
			t.Errorf("verse 25 should not appear in 119:1-24, got line: %q", line)
		}
	}
}

func TestPsalterLookupSingleVerse(t *testing.T) {
	ps, err := LoadPsalter()
	if err != nil {
		t.Fatalf("LoadPsalter: %v", err)
	}
	text := ps.Lookup("117:1-2")
	if text == "" {
		t.Fatal("Lookup(117:1-2): got empty string")
	}
	// Psalm 117 has only 2 verses; both should be present.
	if !strings.Contains(text, "1 ") || !strings.Contains(text, "2 ") {
		t.Errorf("expected both verses of Ps 117, got: %q", text)
	}
}

func TestPsalterLookupInvitatory(t *testing.T) {
	ps, err := LoadPsalter()
	if err != nil {
		t.Fatalf("LoadPsalter: %v", err)
	}
	// "(Invitatory)" suffix should be stripped; full psalm returned.
	text := ps.Lookup("95 (Invitatory)")
	if text == "" {
		t.Fatal("Lookup(95 (Invitatory)): got empty string")
	}
	if !strings.HasPrefix(text, "1 ") {
		t.Errorf("expected verse 1 of Psalm 95, got: %q", text[:min(40, len(text))])
	}
}

func TestPsalterLookupMissing(t *testing.T) {
	ps, err := LoadPsalter()
	if err != nil {
		t.Fatalf("LoadPsalter: %v", err)
	}
	if got := ps.Lookup("999"); got != "" {
		t.Errorf("Lookup(999): expected empty string, got %q", got[:min(40, len(got))])
	}
	if got := ps.Lookup(""); got != "" {
		t.Errorf("Lookup(''): expected empty string, got non-empty")
	}
	if got := ps.Lookup("not a citation"); got != "" {
		t.Errorf("Lookup('not a citation'): expected empty string")
	}
}

func TestPsalterLookupNumber(t *testing.T) {
	ps, err := LoadPsalter()
	if err != nil {
		t.Fatalf("LoadPsalter: %v", err)
	}
	if ps.LookupNumber(23) == "" {
		t.Error("LookupNumber(23): got empty string")
	}
	if ps.LookupNumber(0) != "" {
		t.Error("LookupNumber(0): expected empty string")
	}
}

func TestPsalterNoSmartQuotes(t *testing.T) {
	ps, err := LoadPsalter()
	if err != nil {
		t.Fatalf("LoadPsalter: %v", err)
	}
	curly := "“”‘’"
	for n, e := range ps.psalms {
		for _, c := range curly {
			if strings.ContainsRune(e.Text, c) {
				t.Errorf("psalm %d contains curly quote U+%04X", n, c)
			}
		}
	}
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
