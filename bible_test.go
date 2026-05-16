package lectionary

import (
	"os"
	"strings"
	"testing"
)

func mustLoadBible(t *testing.T) *Bible {
	t.Helper()
	apiKey := os.Getenv("BIBLE_API_KEY")
	if apiKey == "" {
		t.Skip("BIBLE_API_KEY not set — skipping API integration test")
	}
	b, err := LoadBible(apiKey)
	if err != nil {
		t.Fatalf("LoadBible: %v", err)
	}
	return b
}

func TestBibleLoadBible(t *testing.T) {
	b := mustLoadBible(t)
	if b == nil {
		t.Fatal("got nil Bible")
	}
}

func TestBibleSimpleRange(t *testing.T) {
	b := mustLoadBible(t)
	text := b.Lookup("Dan 7:9-14")
	if text == "" {
		t.Fatal("Lookup(Dan 7:9-14): got empty string")
	}
	if !strings.Contains(text, "Ancient of days") {
		t.Errorf("Dan 7:9-14 missing expected text, got: %q", text[:min(80, len(text))])
	}
	// Verse 9 should be the first line; verse 15 should not appear.
	if !strings.HasPrefix(text, "9 ") {
		t.Errorf("expected result to start with verse 9, got: %q", text[:min(40, len(text))])
	}
	for _, line := range strings.Split(text, "\n") {
		if strings.HasPrefix(line, "15 ") {
			t.Error("verse 15 should not appear in Dan 7:9-14")
		}
	}
}

func TestBibleNumberedBook(t *testing.T) {
	b := mustLoadBible(t)
	text := b.Lookup("Heb 2:5-18")
	if text == "" {
		t.Fatal("Lookup(Heb 2:5-18): got empty string")
	}
	if !strings.HasPrefix(text, "5 ") {
		t.Errorf("expected result to start with verse 5, got: %q", text[:min(40, len(text))])
	}
}

func TestBibleNumberedBookPrefix(t *testing.T) {
	b := mustLoadBible(t)
	cases := []struct {
		citation  string
		wantStart string
	}{
		{"1 Cor 13:1-13", "1 "},
		{"2 Kgs 2:1-15", "1 "},
		{"1 Sam 3:1-21", "1 "},
	}
	for _, tc := range cases {
		text := b.Lookup(tc.citation)
		if text == "" {
			t.Errorf("Lookup(%q): got empty string", tc.citation)
			continue
		}
		if !strings.HasPrefix(text, tc.wantStart) {
			t.Errorf("Lookup(%q): expected start %q, got: %q", tc.citation, tc.wantStart, text[:min(40, len(text))])
		}
	}
}

func TestBibleSingleChapterBook(t *testing.T) {
	b := mustLoadBible(t)
	cases := []string{
		"Jude 1-16",
		"2 Jn 1-13",
		"3 Jn 1-15",
		"Ob 15-21",
	}
	for _, citation := range cases {
		text := b.Lookup(citation)
		if text == "" {
			t.Errorf("Lookup(%q): got empty string (single-chapter book should default to chapter 1)", citation)
		}
	}
}

func TestBibleCrossChapterEmDash(t *testing.T) {
	b := mustLoadBible(t)
	text := b.Lookup("Dt 9:23—10:5")
	if text == "" {
		t.Fatal("Lookup(Dt 9:23—10:5): got empty string")
	}
	hasC9 := strings.Contains(text, "23 ")
	hasC10 := false
	for _, line := range strings.Split(text, "\n") {
		if strings.HasPrefix(line, "1 ") {
			hasC10 = true
		}
	}
	if !hasC9 {
		t.Error("expected verse from chapter 9")
	}
	if !hasC10 {
		t.Error("expected verses from chapter 10")
	}
}

func TestBibleCommaRangesSameChapter(t *testing.T) {
	b := mustLoadBible(t)
	text := b.Lookup("Ezek 1:1-14, 24-28b")
	if text == "" {
		t.Fatal("Lookup(Ezek 1:1-14, 24-28b): got empty string")
	}
	hasV1 := strings.HasPrefix(text, "1 ")
	hasV24 := strings.Contains(text, "\n24 ")
	noV15 := true
	for _, line := range strings.Split(text, "\n") {
		if strings.HasPrefix(line, "15 ") {
			noV15 = false
		}
	}
	if !hasV1 {
		t.Error("expected verse 1 in Ezek 1:1-14, 24-28b")
	}
	if !hasV24 {
		t.Error("expected verse 24 in Ezek 1:1-14, 24-28b")
	}
	if !noV15 {
		t.Error("verse 15 should not appear (gap between ranges)")
	}
}

func TestBibleCommaRangesDifferentChapters(t *testing.T) {
	b := mustLoadBible(t)
	text := b.Lookup("Dt 16:18-20, 17:14-20")
	if text == "" {
		t.Fatal("Lookup(Dt 16:18-20, 17:14-20): got empty string")
	}
	if !strings.HasPrefix(text, "18 ") {
		t.Errorf("expected verse 18 first, got: %q", text[:min(40, len(text))])
	}
	if !strings.Contains(text, "\n14 ") {
		t.Error("expected verse 14 from chapter 17")
	}
}

func TestBibleMixedCrossChapter(t *testing.T) {
	b := mustLoadBible(t)
	text := b.Lookup("Am 1:1-5, 13—2:8")
	if text == "" {
		t.Fatal("Lookup(Am 1:1-5, 13—2:8): got empty string")
	}
	if !strings.HasPrefix(text, "1 ") {
		t.Errorf("expected verse 1 first, got: %q", text[:min(40, len(text))])
	}
}

func TestBibleAlternativePicksFirst(t *testing.T) {
	b := mustLoadBible(t)
	text := b.Lookup("Jn 1:1-14 or Gen 1:1-5")
	if text == "" {
		t.Fatal("Lookup(A or B): got empty")
	}
	// Should be John, not Genesis.
	if strings.Contains(text, "God created") {
		t.Error("should use first alternative (John), not Genesis")
	}
}

func TestBibleMissingCitation(t *testing.T) {
	b := mustLoadBible(t)
	if got := b.Lookup(""); got != "" {
		t.Error("empty citation should return empty string")
	}
	if got := b.Lookup("Xyz 1:1"); got != "" {
		t.Error("unknown book should return empty string")
	}
}

func TestBibleNoSuperscripts(t *testing.T) {
	b := mustLoadBible(t)
	text := b.Lookup("Gen 1:1-3")
	superscripts := "⁰¹²³⁴⁵⁶⁷⁸⁹"
	for _, c := range superscripts {
		if strings.ContainsRune(text, c) {
			t.Errorf("verse text contains superscript character U+%04X", c)
		}
	}
}

func TestBibleNilSafe(t *testing.T) {
	var b *Bible
	if got := b.Lookup("Jn 1:1"); got != "" {
		t.Error("nil Bible.Lookup should return empty string")
	}
	if got := b.Copyright(); got != "" {
		t.Error("nil Bible.Copyright should return empty string")
	}
}
