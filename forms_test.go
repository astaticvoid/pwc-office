package lectionary_test

import (
	"strings"
	"testing"
	"time"

	lectionary "github.com/astaticvoid/pwc-office"
)

func TestLoadForms(t *testing.T) {
	f, err := lectionary.LoadForms()
	if err != nil {
		t.Fatalf("LoadForms: %v", err)
	}
	if f == nil {
		t.Fatal("LoadForms returned nil")
	}
}

func TestFormsLookupSeasonal(t *testing.T) {
	f, err := lectionary.LoadForms()
	if err != nil {
		t.Fatalf("LoadForms: %v", err)
	}

	cases := []struct {
		season   string
		office   string
		weekday  time.Weekday
		wantFrag string // fragment expected somewhere in opening_responses leader/response text
	}{
		{"Advent", "mp", time.Sunday, "Creator of the stars"},
		{"Christmas", "mp", time.Sunday, "incarnate Word"},
		{"Easter", "mp", time.Sunday, "Christ is risen"},
		{"Lent", "ep", time.Sunday, ""},
		{"Passiontide", "mp", time.Sunday, ""},
		{"AllSaints", "ep", time.Sunday, ""},
	}

	for _, c := range cases {
		form := f.Lookup(c.season, c.office, c.weekday)
		if form == nil {
			t.Errorf("Lookup(%q, %q): got nil", c.season, c.office)
			continue
		}
		if form.Title == "" {
			t.Errorf("Lookup(%q, %q): empty title", c.season, c.office)
		}
		if c.wantFrag != "" {
			if len(form.OpeningResponses) == 0 {
				t.Errorf("Lookup(%q, %q): OpeningResponses is empty", c.season, c.office)
				continue
			}
			found := false
			for _, seg := range form.OpeningResponses {
				if strings.Contains(seg.Text, c.wantFrag) {
					found = true
					break
				}
			}
			if !found {
				t.Errorf("Lookup(%q, %q): %q not found in OpeningResponses", c.season, c.office, c.wantFrag)
			}
		}
	}
}

func TestFormsLookupOrdinaryTime(t *testing.T) {
	f, err := lectionary.LoadForms()
	if err != nil {
		t.Fatalf("LoadForms: %v", err)
	}

	weekdays := []time.Weekday{
		time.Sunday, time.Monday, time.Tuesday, time.Wednesday,
		time.Thursday, time.Friday, time.Saturday,
	}
	for _, wd := range weekdays {
		for _, ot := range []string{"mp", "ep"} {
			form := f.Lookup("OrdinaryTime", ot, wd)
			if form == nil {
				t.Errorf("Lookup(OrdinaryTime, %s, %s): got nil", ot, wd)
				continue
			}
			if form.Title == "" {
				t.Errorf("Lookup(OrdinaryTime, %s, %s): empty title", ot, wd)
			}
		}
	}
}

func TestFormsLookupMissing(t *testing.T) {
	f, err := lectionary.LoadForms()
	if err != nil {
		t.Fatalf("LoadForms: %v", err)
	}
	if got := f.Lookup("Unknown", "mp", time.Sunday); got != nil {
		t.Errorf("expected nil for unknown season, got %+v", got)
	}
}

func TestFormsOrdinaryMPHasInvitatory(t *testing.T) {
	f, err := lectionary.LoadForms()
	if err != nil {
		t.Fatalf("LoadForms: %v", err)
	}
	form := f.Lookup("OrdinaryTime", "mp", time.Wednesday)
	if form == nil {
		t.Fatal("Lookup(OrdinaryTime, mp, Wednesday) returned nil")
	}
	if len(form.Invitatory) == 0 {
		t.Error("ordinary-wednesday-mp: expected non-empty Invitatory")
	}
}

func TestFormsSeasonalHasSeasonalCollects(t *testing.T) {
	f, err := lectionary.LoadForms()
	if err != nil {
		t.Fatalf("LoadForms: %v", err)
	}
	for _, season := range []string{"Advent", "Christmas", "Lent", "Easter"} {
		form := f.Lookup(season, "mp", time.Sunday)
		if form == nil {
			t.Errorf("%s MP: nil form", season)
			continue
		}
		if len(form.SeasonalCollects) == 0 {
			t.Errorf("%s MP: expected non-empty SeasonalCollects", season)
		}
	}
}

func TestFormsSegmentTypes(t *testing.T) {
	f, err := lectionary.LoadForms()
	if err != nil {
		t.Fatalf("LoadForms: %v", err)
	}
	form := f.Lookup("Easter", "mp", time.Sunday)
	if form == nil {
		t.Fatal("Easter mp: nil form")
	}

	// Opening responses must contain all three segment types.
	types := map[string]bool{}
	for _, seg := range form.OpeningResponses {
		types[seg.Type] = true
	}
	for _, want := range []string{"leader", "response", "rubric"} {
		if !types[want] {
			t.Errorf("Easter mp opening_responses: missing segment type %q", want)
		}
	}

	// Every segment must have non-empty text and a known type.
	valid := map[string]bool{"leader": true, "response": true, "rubric": true}
	for _, seg := range form.OpeningResponses {
		if seg.Text == "" {
			t.Errorf("empty text in segment type=%q", seg.Type)
		}
		if !valid[seg.Type] {
			t.Errorf("unknown segment type %q", seg.Type)
		}
	}
}
