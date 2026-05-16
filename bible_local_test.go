package lectionary

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// mustLoadNRSVUE loads the local NRSVUE bible from the XDG data dir.
// Skips the test if the data directory is not present.
func mustLoadNRSVUE(t *testing.T) *LocalBible {
	t.Helper()
	home, _ := os.UserHomeDir()
	dir := filepath.Join(home, ".local", "share", "pwc_office", "translations", "nrsvue")
	b, err := LoadLocalBible("nrsvue", dir)
	if err != nil {
		t.Skipf("NRSVUE data not found at %s — skipping", dir)
	}
	return b
}

// ── KJV (embedded, always available) ─────────────────────────────────────────

func TestKJVNotNil(t *testing.T) {
	if KJV() == nil {
		t.Fatal("KJV() returned nil")
	}
}

func TestKJVSimpleRange(t *testing.T) {
	b := KJV()
	text := b.Lookup("Jn 1:1-5")
	if text == "" {
		t.Fatal("Lookup(Jn 1:1-5): got empty string")
	}
	if !strings.HasPrefix(text, "1 ") {
		t.Errorf("expected verse 1 first, got: %q", text[:min(40, len(text))])
	}
	if !strings.Contains(text, "Word") {
		t.Error("Jn 1:1-5 (KJV) should contain 'Word'")
	}
	for _, line := range strings.Split(text, "\n") {
		if strings.HasPrefix(line, "6 ") {
			t.Error("verse 6 should not appear in Jn 1:1-5")
		}
	}
}

func TestKJVGenesis(t *testing.T) {
	b := KJV()
	text := b.Lookup("Gen 1:1-3")
	if text == "" {
		t.Fatal("Lookup(Gen 1:1-3): got empty string")
	}
	if !strings.Contains(text, "heaven and the earth") {
		t.Errorf("Gen 1:1 (KJV) missing expected text, got: %q", text[:min(80, len(text))])
	}
}

func TestKJVSingleChapterBook(t *testing.T) {
	b := KJV()
	cases := []string{
		"Jude 1-16",
		"Philem 1-10",
		"Ob 1-10",
	}
	for _, citation := range cases {
		text := b.Lookup(citation)
		if text == "" {
			t.Errorf("Lookup(%q): got empty string (single-chapter book)", citation)
		}
	}
}

func TestKJVCrossChapterEmDash(t *testing.T) {
	b := KJV()
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
		t.Error("expected verse from Deuteronomy 9")
	}
	if !hasC10 {
		t.Error("expected verses from Deuteronomy 10")
	}
}

func TestKJVCommaRangesSameChapter(t *testing.T) {
	b := KJV()
	text := b.Lookup("Num 11:16-17, 24-25")
	if text == "" {
		t.Fatal("Lookup(Num 11:16-17, 24-25): got empty string")
	}
	if !strings.HasPrefix(text, "16 ") {
		t.Errorf("expected verse 16 first, got: %q", text[:min(40, len(text))])
	}
	if !strings.Contains(text, "\n24 ") {
		t.Error("expected verse 24 to appear after the gap")
	}
	for _, line := range strings.Split(text, "\n") {
		if strings.HasPrefix(line, "18 ") {
			t.Error("verse 18 should not appear (gap between ranges)")
		}
	}
}

func TestKJVAlternativePicksFirst(t *testing.T) {
	b := KJV()
	text := b.Lookup("Jn 1:1-5 or Gen 1:1-3")
	if text == "" {
		t.Fatal("Lookup(A or B): got empty string")
	}
	if !strings.Contains(text, "Word") {
		t.Error("should use first alternative (John), not Genesis")
	}
}

func TestKJVApocrypha(t *testing.T) {
	b := KJV()
	cases := []struct {
		citation string
		want     string
	}{
		{"Sir 48:1-3", "Elias"},       // KJV uses "Elias" for Elijah
		{"2 Esd 2:42-44", "Esdras"},   // 2 Esdras present
		{"Tob 1:1-3", "Tobit"},         // Tobit
		{"Wis 7:1-7", "mortal man"},   // Wisdom of Solomon
	}
	for _, tc := range cases {
		text := b.Lookup(tc.citation)
		if text == "" {
			t.Errorf("Lookup(%q): got empty string", tc.citation)
			continue
		}
		if !strings.Contains(text, tc.want) {
			t.Errorf("Lookup(%q): expected %q in text, got: %q", tc.citation, tc.want, text[:min(80, len(text))])
		}
	}
}

func TestKJVMissingCitation(t *testing.T) {
	b := KJV()
	if got := b.Lookup(""); got != "" {
		t.Error("empty citation should return empty string")
	}
	if got := b.Lookup("Xyz 1:1"); got != "" {
		t.Error("unknown book should return empty string")
	}
}

func TestLocalBibleNilSafe(t *testing.T) {
	var b *LocalBible
	if got := b.Lookup("Jn 1:1"); got != "" {
		t.Error("nil LocalBible.Lookup should return empty string")
	}
	if got := b.Copyright(); got != "" {
		t.Error("nil LocalBible.Copyright should return empty string")
	}
	if got := b.Translation(); got != "" {
		t.Error("nil LocalBible.Translation should return empty string")
	}
	if got := b.AttributionURL(); got != "" {
		t.Error("nil LocalBible.AttributionURL should return empty string")
	}
}

// ── NRSVUE (local data, skipped if not present) ───────────────────────────────

func TestNRSVUESimpleRange(t *testing.T) {
	b := mustLoadNRSVUE(t)
	text := b.Lookup("Jn 1:1-5")
	if text == "" {
		t.Fatal("Lookup(Jn 1:1-5): got empty string")
	}
	if !strings.HasPrefix(text, "1 ") {
		t.Errorf("expected verse 1 first, got: %q", text[:min(40, len(text))])
	}
	if !strings.Contains(text, "Word") {
		t.Error("Jn 1:1 (NRSVUE) should contain 'Word'")
	}
}

func TestNRSVUEApocrypha(t *testing.T) {
	b := mustLoadNRSVUE(t)
	text := b.Lookup("Sir 48:1-3")
	if text == "" {
		t.Fatal("Lookup(Sir 48:1-3): got empty string")
	}
	// NRSVUE uses "Elijah" where KJV uses "Elias"
	if !strings.Contains(text, "Elijah") {
		t.Errorf("Sir 48:1 (NRSVUE) expected 'Elijah', got: %q", text[:min(80, len(text))])
	}
}

func TestNRSVUECrossChapterEmDash(t *testing.T) {
	b := mustLoadNRSVUE(t)
	text := b.Lookup("Dt 9:23—10:5")
	if text == "" {
		t.Fatal("Lookup(Dt 9:23—10:5): got empty string")
	}
	if !strings.Contains(text, "23 ") {
		t.Error("expected verse from Deuteronomy 9")
	}
}
