//go:build e2e_smoke || e2e_seasonal || e2e_full

package e2e_test

import (
	"strings"
	"testing"
	"time"

	lectionary "github.com/astaticvoid/pwc-office"
	"github.com/astaticvoid/pwc-office/internal/office"
)

// renderOffice looks up the given date and renders the requested office type.
// It returns the rendered Markdown and the Day record.
func renderOffice(t *testing.T, dateStr, officeType string) (string, *lectionary.Day) {
	t.Helper()

	d, err := time.Parse("2006-01-02", dateStr)
	if err != nil {
		t.Fatalf("invalid date %q: %v", dateStr, err)
	}

	l, err := lectionary.Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	ps, err := lectionary.LoadPsalter()
	if err != nil {
		t.Fatalf("LoadPsalter: %v", err)
	}
	bible, err := lectionary.LoadBible()
	if err != nil {
		t.Fatalf("LoadBible: %v", err)
	}
	collects, err := lectionary.LoadCollects()
	if err != nil {
		t.Fatalf("LoadCollects: %v", err)
	}
	forms, err := lectionary.LoadForms()
	if err != nil {
		t.Fatalf("LoadForms: %v", err)
	}

	day, err := l.Lookup(d)
	if err != nil {
		t.Fatalf("Lookup(%s): %v", dateStr, err)
	}

	rendered := office.Render(day, officeType, ps, bible, collects, forms)
	return rendered, day
}

// checkStructure verifies the required sections are present in rendered Markdown.
// This is the structural (non-LLM) check used by all suites.
func checkStructure(t *testing.T, rendered, label string) {
	t.Helper()
	required := []string{
		"## The Gathering of the Community",
		"## The Proclamation of the Word",
		"### The Psalm:",
		"### The Reading:",
		"## The Prayers of the Community",
		"### The Lord's Prayer",
		"## The Sending Forth of the Community",
	}
	for _, section := range required {
		if !strings.Contains(rendered, section) {
			t.Errorf("%s: missing section %q", label, section)
		}
	}

	// Ensure Lord's Prayer body is present.
	if !strings.Contains(rendered, "Our Father") {
		t.Errorf("%s: Lord's Prayer body absent", label)
	}
	// Ensure dismissal has content.
	idx := strings.Index(rendered, "## The Sending Forth")
	if idx >= 0 && strings.TrimSpace(rendered[idx:]) == "## The Sending Forth of the Community" {
		t.Errorf("%s: Sending Forth section is empty", label)
	}
}
