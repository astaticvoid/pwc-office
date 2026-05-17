package lectionary_test

import (
	"strings"
	"testing"
	"time"

	lectionary "github.com/astaticvoid/pwc-office"
)

// allOfficeKeys enumerates every office key present in the embedded data.
var allOfficeKeys = []struct{ key, season, office string }{
	{"advent-mp", "Advent", "mp"},
	{"advent-ep", "Advent", "ep"},
	{"christmas-mp", "Christmas", "mp"},
	{"christmas-ep", "Christmas", "ep"},
	{"epiphany-mp", "Epiphany", "mp"},
	{"epiphany-ep", "Epiphany", "ep"},
	{"lent-mp", "Lent", "mp"},
	{"lent-ep", "Lent", "ep"},
	{"passiontide-mp", "Passiontide", "mp"},
	{"passiontide-ep", "Passiontide", "ep"},
	{"easter-mp", "Easter", "mp"},
	{"easter-ep", "Easter", "ep"},
	{"pentecost-mp", "Pentecost", "mp"},
	{"pentecost-ep", "Pentecost", "ep"},
	{"allsaints-mp", "AllSaints", "mp"},
	{"allsaints-ep", "AllSaints", "ep"},
	{"ordinary-sunday-mp", "OrdinaryTime", "mp"},
	{"ordinary-sunday-ep", "OrdinaryTime", "ep"},
	{"ordinary-monday-mp", "OrdinaryTime", "mp"},
	{"ordinary-monday-ep", "OrdinaryTime", "ep"},
	{"ordinary-tuesday-mp", "OrdinaryTime", "mp"},
	{"ordinary-tuesday-ep", "OrdinaryTime", "ep"},
	{"ordinary-wednesday-mp", "OrdinaryTime", "mp"},
	{"ordinary-wednesday-ep", "OrdinaryTime", "ep"},
	{"ordinary-thursday-mp", "OrdinaryTime", "mp"},
	{"ordinary-thursday-ep", "OrdinaryTime", "ep"},
	{"ordinary-friday-mp", "OrdinaryTime", "mp"},
	{"ordinary-friday-ep", "OrdinaryTime", "ep"},
	{"ordinary-saturday-mp", "OrdinaryTime", "mp"},
	{"ordinary-saturday-ep", "OrdinaryTime", "ep"},
}

func TestLoadForms(t *testing.T) {
	f, err := lectionary.LoadForms()
	if err != nil {
		t.Fatalf("LoadForms: %v", err)
	}
	if f == nil {
		t.Fatal("LoadForms returned nil")
	}
}

// segContains reports whether fragment appears in any segment text,
// recursively searching into alternatives groups.
func segContains(segs []lectionary.Segment, fragment string) bool {
	for _, seg := range segs {
		if strings.Contains(seg.Text, fragment) {
			return true
		}
		for _, g := range seg.Groups {
			if segContains(g.Segments, fragment) {
				return true
			}
		}
	}
	return false
}

// segTypes collects all segment types, recursively searching alternatives.
func segTypes(segs []lectionary.Segment, out map[string]bool) {
	for _, seg := range segs {
		out[seg.Type] = true
		for _, g := range seg.Groups {
			segTypes(g.Segments, out)
		}
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
			if !segContains(form.OpeningResponses, c.wantFrag) {
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

	// Opening responses must contain all three leaf segment types (searched recursively).
	types := map[string]bool{}
	segTypes(form.OpeningResponses, types)
	for _, want := range []string{"leader", "response"} {
		if !types[want] {
			t.Errorf("Easter mp opening_responses: missing segment type %q", want)
		}
	}

	// Every top-level segment must have a known type; leaf segments must have non-empty text.
	valid := map[string]bool{"leader": true, "response": true, "rubric": true, "alternatives": true, "shared": true}
	var checkSegs func(segs []lectionary.Segment)
	checkSegs = func(segs []lectionary.Segment) {
		for _, seg := range segs {
			if !valid[seg.Type] {
				t.Errorf("unknown segment type %q", seg.Type)
			}
			noText := seg.Type == "alternatives" || seg.Type == "shared"
			if !noText && seg.Text == "" {
				t.Errorf("empty text in segment type=%q", seg.Type)
			}
			for _, g := range seg.Groups {
				checkSegs(g.Segments)
			}
		}
	}
	checkSegs(form.OpeningResponses)
}

// TestFormsAllOfficesLoad verifies every known office key loads without error.
func TestFormsAllOfficesLoad(t *testing.T) {
	f, err := lectionary.LoadForms()
	if err != nil {
		t.Fatalf("LoadForms: %v", err)
	}
	weekdays := map[string]time.Weekday{
		"sunday": time.Sunday, "monday": time.Monday, "tuesday": time.Tuesday,
		"wednesday": time.Wednesday, "thursday": time.Thursday,
		"friday": time.Friday, "saturday": time.Saturday,
	}
	for _, tc := range allOfficeKeys {
		wd := time.Sunday
		for day, w := range weekdays {
			if strings.Contains(tc.key, day) {
				wd = w
				break
			}
		}
		form := f.Lookup(tc.season, tc.office, wd)
		if form == nil {
			t.Errorf("%s: Lookup returned nil", tc.key)
			continue
		}
		if form.Title == "" {
			t.Errorf("%s: empty title", tc.key)
		}
		if len(form.Canticle) == 0 {
			t.Errorf("%s: empty Canticle section", tc.key)
		}
		if len(form.Dismissal) == 0 {
			t.Errorf("%s: empty Dismissal section", tc.key)
		}
	}
}

// TestFormsCanticleAlternatives verifies every office has a canticle
// alternatives block with at least 3 named groups and a doxology block.
func TestFormsCanticleAlternatives(t *testing.T) {
	f, err := lectionary.LoadForms()
	if err != nil {
		t.Fatalf("LoadForms: %v", err)
	}
	weekdays := map[string]time.Weekday{
		"sunday": time.Sunday, "monday": time.Monday, "tuesday": time.Tuesday,
		"wednesday": time.Wednesday, "thursday": time.Thursday,
		"friday": time.Friday, "saturday": time.Saturday,
	}
	for _, tc := range allOfficeKeys {
		wd := time.Sunday
		for day, w := range weekdays {
			if strings.Contains(tc.key, day) {
				wd = w
				break
			}
		}
		form := f.Lookup(tc.season, tc.office, wd)
		if form == nil {
			t.Errorf("%s: nil form", tc.key)
			continue
		}

		var altBlocks []lectionary.Segment
		for _, seg := range form.Canticle {
			resolved := f.Resolve(seg)
			if resolved.Type == "alternatives" {
				altBlocks = append(altBlocks, resolved)
			}
		}
		if len(altBlocks) < 2 {
			t.Errorf("%s: want ≥2 alternatives blocks in canticle, got %d", tc.key, len(altBlocks))
			continue
		}
		// First block: 3 named canticle choices.
		main := altBlocks[0]
		if len(main.Groups) != 3 {
			t.Errorf("%s: canticle main block: want 3 groups, got %d", tc.key, len(main.Groups))
		}
		for _, g := range main.Groups {
			if g.Label == "" {
				t.Errorf("%s: canticle group has empty label", tc.key)
			}
			if len(g.Segments) == 0 {
				t.Errorf("%s: canticle group %q is empty", tc.key, g.Label)
			}
		}
		// Second block: 3 doxology options (Roman numerals).
		dox := altBlocks[1]
		if len(dox.Groups) != 3 {
			t.Errorf("%s: doxology block: want 3 groups, got %d", tc.key, len(dox.Groups))
		}
		for _, g := range dox.Groups {
			if len(g.Segments) == 0 {
				t.Errorf("%s: doxology group %q is empty", tc.key, g.Label)
			}
			// Each doxology group must contain at least one leader + one response.
			if !segContains(g.Segments, "Glory") {
				t.Errorf("%s: doxology group %q missing 'Glory'", tc.key, g.Label)
			}
		}
	}
}

// TestFormsAffirmationAlternatives verifies every office affirmation section
// has exactly 2 alternatives (Apostles' Creed and Hear, O Israel).
func TestFormsAffirmationAlternatives(t *testing.T) {
	f, err := lectionary.LoadForms()
	if err != nil {
		t.Fatalf("LoadForms: %v", err)
	}
	weekdays := map[string]time.Weekday{
		"sunday": time.Sunday, "monday": time.Monday, "tuesday": time.Tuesday,
		"wednesday": time.Wednesday, "thursday": time.Thursday,
		"friday": time.Friday, "saturday": time.Saturday,
	}
	for _, tc := range allOfficeKeys {
		wd := time.Sunday
		for day, w := range weekdays {
			if strings.Contains(tc.key, day) {
				wd = w
				break
			}
		}
		form := f.Lookup(tc.season, tc.office, wd)
		if form == nil || len(form.Affirmation) == 0 {
			continue
		}
		var altBlock lectionary.Segment
		var found bool
		for _, seg := range form.Affirmation {
			resolved := f.Resolve(seg)
			if resolved.Type == "alternatives" {
				altBlock = resolved
				found = true
				break
			}
		}
		if !found {
			t.Errorf("%s: affirmation has no alternatives block", tc.key)
			continue
		}
		if len(altBlock.Groups) != 2 {
			t.Errorf("%s: affirmation: want 2 groups, got %d", tc.key, len(altBlock.Groups))
			continue
		}
		if !strings.Contains(altBlock.Groups[0].Label, "Apostles") {
			t.Errorf("%s: affirmation group 0: want 'Apostles' in label, got %q", tc.key, altBlock.Groups[0].Label)
		}
		if !strings.Contains(altBlock.Groups[1].Label, "Hear") {
			t.Errorf("%s: affirmation group 1: want 'Hear' in label, got %q", tc.key, altBlock.Groups[1].Label)
		}
	}
}

// TestFormsNoOrphanedOrRubrics ensures no Or/or rubrics remain at the top
// level of any section after alternatives grouping.
func TestFormsNoOrphanedOrRubrics(t *testing.T) {
	f, err := lectionary.LoadForms()
	if err != nil {
		t.Fatalf("LoadForms: %v", err)
	}
	weekdays := map[string]time.Weekday{
		"sunday": time.Sunday, "monday": time.Monday, "tuesday": time.Tuesday,
		"wednesday": time.Wednesday, "thursday": time.Thursday,
		"friday": time.Friday, "saturday": time.Saturday,
	}
	for _, tc := range allOfficeKeys {
		wd := time.Sunday
		for day, w := range weekdays {
			if strings.Contains(tc.key, day) {
				wd = w
				break
			}
		}
		form := f.Lookup(tc.season, tc.office, wd)
		if form == nil {
			continue
		}
		sections := map[string][]lectionary.Segment{
			"opening_responses": form.OpeningResponses,
			"canticle":          form.Canticle,
			"affirmation":       form.Affirmation,
			"responsory":        form.Responsory,
		}
		for sectionName, segs := range sections {
			for _, seg := range segs {
				if seg.Type == "rubric" {
					txt := strings.TrimSpace(seg.Text)
					if txt == "Or" || txt == "or" || strings.HasPrefix(txt, "Or\n") {
						t.Errorf("%s.%s: orphaned Or/or rubric at top level: %q",
							tc.key, sectionName, txt[:min(40, len(txt))])
					}
				}
			}
		}
	}
}
