//go:build e2e_smoke || e2e_seasonal

package e2e_test

import (
	"fmt"
	"io"
	"net/http"
	"regexp"
	"strings"
	"testing"
)

// officialReadings holds citations fetched from lectionary.anglican.ca for one
// office on one day.
type officialReadings struct {
	Psalms   []string // e.g. ["148", "149", "150"]
	Readings []string // e.g. ["Ex 12:1-14", "Jn 1:1-18"]
	Collect  string   // e.g. "335"
	Raw      string   // the full citation string from the site, for logging
}

var (
	reMPEntry = regexp.MustCompile(`id='lectionary_MP'[^>]*>(.*?)</p>`)
	reEPEntry = regexp.MustCompile(`id='lectionary_EP'[^>]*>(.*?)</p>`)
	reTagStrip = regexp.MustCompile(`<[^>]+>`)
	reHTMLEnt  = strings.NewReplacer(
		"&mdash;", "—", "&ndash;", "–", "&amp;", "&",
		"&lt;", "<", "&gt;", ">", "&nbsp;", " ",
	)
)

// fetchOfficialReadings retrieves the BAS lectionary citations for the given date
// from lectionary.anglican.ca and parses them into structured form.
// The test is skipped (not failed) if the site is unreachable.
func fetchOfficialReadings(t *testing.T, date, officeType string) *officialReadings {
	t.Helper()

	url := "https://lectionary.anglican.ca/?date=" + date
	resp, err := http.Get(url)
	if err != nil {
		t.Skipf("lectionary.anglican.ca unreachable (%v) — skipping official-reading verification", err)
		return nil
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Skipf("reading lectionary response: %v", err)
		return nil
	}
	html := string(body)

	var re *regexp.Regexp
	switch officeType {
	case "ep":
		re = reEPEntry
	default:
		re = reMPEntry
	}

	m := re.FindStringSubmatch(html)
	if m == nil {
		t.Logf("WARNING: could not locate %s entry on lectionary.anglican.ca for %s", officeType, date)
		return nil
	}

	// Strip HTML tags and decode entities.
	raw := reTagStrip.ReplaceAllString(m[1], "")
	raw = reHTMLEnt.Replace(raw)
	raw = strings.TrimSpace(raw)

	// Remove "Morning Prayer:" / "Evening Prayer:" label.
	if idx := strings.Index(raw, ":"); idx >= 0 {
		raw = strings.TrimSpace(raw[idx+1:])
	}

	t.Logf("official readings (%s %s): %s", officeType, date, raw)

	return parseCitations(raw)
}

// parseCitations splits a semicolon-delimited citation string into structured fields.
// Format: "Ps 148, 149, 150; Ex 12:1-14; Jn 1:1-18; Coll 335"
func parseCitations(raw string) *officialReadings {
	or := &officialReadings{Raw: raw}
	for _, part := range strings.Split(raw, ";") {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		switch {
		case strings.HasPrefix(part, "Ps "):
			// "Ps 148, 149, 150" → ["148", "149", "150"]
			nums := strings.TrimPrefix(part, "Ps ")
			for _, n := range strings.Split(nums, ",") {
				or.Psalms = append(or.Psalms, strings.TrimSpace(n))
			}
		case strings.HasPrefix(part, "Coll "):
			or.Collect = strings.TrimPrefix(part, "Coll ")
		default:
			// Reading — may have "or" alternatives; keep the full string.
			or.Readings = append(or.Readings, part)
		}
	}
	return or
}

// verifyReadings checks that citations from the official lectionary appear in
// the rendered office output. Logs mismatches as errors (not fatal).
func verifyReadings(t *testing.T, label string, rendered string, or *officialReadings) {
	t.Helper()
	if or == nil {
		return
	}

	// Psalm check: at least one official psalm number must appear in the heading.
	psHeadingIdx := strings.Index(rendered, "### The Psalm:")
	psSection := ""
	if psHeadingIdx >= 0 {
		psSection = rendered[psHeadingIdx : psHeadingIdx+80]
	}
	psFound := false
	for _, ps := range or.Psalms {
		if strings.Contains(psSection, ps) {
			psFound = true
			break
		}
	}
	if !psFound && len(or.Psalms) > 0 {
		t.Errorf("%s: official psalms %v not found in psalm heading %q",
			label, or.Psalms, psSection)
	}

	// Reading check: each official reading citation (or one of its "or" alternatives)
	// must appear somewhere in the rendered output.
	for _, reading := range or.Readings {
		alts := strings.Split(reading, " or ")
		found := false
		for _, alt := range alts {
			alt = strings.TrimSpace(alt)
			if strings.Contains(rendered, alt) {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("%s: official reading %q not found in rendered output", label, reading)
		}
	}

	// Collect page check.
	if or.Collect != "" {
		if !strings.Contains(rendered, fmt.Sprintf("p. %s", or.Collect)) {
			t.Errorf("%s: collect page %q not referenced in rendered output", label, or.Collect)
		}
	}
}
