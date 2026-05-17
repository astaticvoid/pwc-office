// Package office renders a Daily Office as Markdown.
// It combines the canonical PWC liturgical form (gathering, prayers, sending)
// with appointed psalms, lessons, and collects from the lectionary.
package office

import (
	"fmt"
	"strings"

	lectionary "github.com/astaticvoid/pwc-office"
)

// Render produces Markdown for the Daily Office on the given day.
// officeType is "mp" (Morning Prayer) or "ep" (Evening Prayer).
// Any of ps, bible, collects, forms may be nil; text is embedded only when available.
func Render(day *lectionary.Day, officeType string, ps *lectionary.Psalter, bible lectionary.BibleSource, collects *lectionary.Collects, forms *lectionary.Forms) string {
	o := selectOffice(day, officeType)

	var form *lectionary.Form
	if forms != nil {
		season := day.Season.String()
		// Pentecost season covers ~6 months. Only Pentecost Sunday itself (a
		// PrincipalFeast) uses the pentecost-{mp|ep} form; all other days in
		// the season use the ordinary weekday forms (ordinary-{weekday}-{mp|ep}).
		if day.Season == lectionary.Pentecost && day.Rank != lectionary.PrincipalFeast {
			season = "OrdinaryTime"
		}
		form = forms.Lookup(season, officeType, day.Weekday)
	}

	var b strings.Builder
	w := func(format string, args ...any) {
		fmt.Fprintf(&b, format+"\n", args...)
	}

	// ── Header ─────────────────────────────────────────────────────────────
	w("# %s — %s", officeName(officeType), day.Name)
	w("")
	w("%s, %s", day.Weekday.String(), day.Date.Format("2 January 2006"))
	w("")
	w("Season: %s | Rank: %s | Colour: %s", day.Season, day.Rank, day.Colour)

	for _, note := range day.Notes {
		w("")
		w("*%s*", note.Text)
	}

	w("")
	w("---")

	// ── The Gathering of the Community ─────────────────────────────────────
	if form != nil && (len(form.OpeningResponses) > 0 || len(form.Invitatory) > 0) {
		w("")
		w("## The Gathering of the Community")
		writeSegments(&b, "Introductory Responses", form.OpeningResponses, forms)
		writeSegments(&b, "Invitatory Psalm", form.Invitatory, forms)
	}

	// ── The Proclamation of the Word ───────────────────────────────────────
	w("")
	w("---")
	w("")
	w("## The Proclamation of the Word")

	if o.Label != "" {
		w("")
		w("### %s", o.Label)
	}
	writeReadings(&b, o, ps, bible, collects)

	if o.Alternate != nil {
		w("")
		w("---")
		if o.Alternate.Label != "" {
			w("")
			w("### %s", o.Alternate.Label)
		}
		writeReadings(&b, *o.Alternate, ps, bible, collects)
	}

	if form != nil {
		writeSegments(&b, "The Responsory", form.Responsory, forms)
		writeSegments(&b, "The Canticle", form.Canticle, forms)
	}

	// ── The Prayers of the Community ───────────────────────────────────────
	if form != nil && (len(form.Affirmation) > 0 || len(form.Litany) > 0) {
		w("")
		w("---")
		w("")
		w("## The Prayers of the Community")
		writeSegments(&b, "Affirmation of Faith", form.Affirmation, forms)
		writeSegments(&b, "The Litany", form.Litany, forms)
		writeSegments(&b, "Seasonal Collects", form.SeasonalCollects, forms)
		if len(form.LordsPrayerIntro) > 0 {
			w("")
			w("### The Lord's Prayer")
			writeSegmentContent(&b, form.LordsPrayerIntro, forms)
		}
	}

	// ── The Sending Forth of the Community ────────────────────────────────
	if form != nil && len(form.Dismissal) > 0 {
		w("")
		w("---")
		w("")
		w("## The Sending Forth of the Community")
		writeSegmentContent(&b, form.Dismissal, forms)
	}

	// ── Scripture attribution (TOS requirement) ────────────────────────────
	if bible != nil {
		w("")
		w("---")
		writeAttribution(&b, bible)
	}

	return b.String()
}

// writeSegments appends a sub-section heading and its typed segments.
func writeSegments(b *strings.Builder, title string, segs []lectionary.Segment, forms *lectionary.Forms) {
	if len(segs) == 0 {
		return
	}
	fmt.Fprintf(b, "\n### %s\n\n", title)
	writeSegmentContent(b, segs, forms)
}

// writeSegmentContent renders segment content without a heading.
func writeSegmentContent(b *strings.Builder, segs []lectionary.Segment, forms *lectionary.Forms) {
	w := func(format string, args ...any) {
		fmt.Fprintf(b, format+"\n", args...)
	}
	for _, seg := range segs {
		if seg.Type == "shared" && forms != nil {
			seg = forms.Resolve(seg)
		}
		switch seg.Type {
		case "rubric":
			for _, line := range strings.Split(seg.Text, "\n") {
				if line = strings.TrimSpace(line); line != "" {
					w("*%s*", line)
				}
			}
		case "response":
			w("**%s**", seg.Text)
		case "alternatives":
			// Render first group (default choice) for CLI output.
			if len(seg.Groups) > 0 {
				writeSegmentContent(b, seg.Groups[0].Segments, forms)
			}
		default: // leader
			w("%s", seg.Text)
		}
	}
}

// writeReadings appends psalms, lessons, and collect for one Office to b.
func writeReadings(b *strings.Builder, o lectionary.Office, ps *lectionary.Psalter, bible lectionary.BibleSource, collects *lectionary.Collects) {
	w := func(format string, args ...any) {
		fmt.Fprintf(b, format+"\n", args...)
	}

	// ── Psalms ───────────────────────────────────────────────────────────
	w("")
	heading := "### The Psalm: " + psalmDisplay(o)
	if o.YearNote != "" {
		heading += fmt.Sprintf(" (Year %s)", o.YearNote)
	}
	w("%s", heading)
	w("")

	if ps != nil {
		for _, psalm := range o.Psalms {
			text := ps.Lookup(psalm.Citation)
			if text != "" {
				w("%s", text)
				w("")
			}
		}
	}

	// ── Lessons ──────────────────────────────────────────────────────────
	if len(o.Lessons) > 0 {
		if o.LessonsPick > 0 {
			w("*Two of the following %d readings:*", len(o.Lessons))
			w("")
		}
		for _, lesson := range o.Lessons {
			citation := lesson.Citation
			if lesson.Optional {
				citation = "(" + citation + ")"
			}
			w("### The Reading: %s", citation)
			w("")
			if bible != nil {
				if text := bible.Lookup(lesson.Citation); text != "" {
					w("%s", text)
					w("")
				}
			}
			w("The word of the Lord.")
			w("**Thanks be to God.**")
			w("")
		}
	}

	// ── Collect ──────────────────────────────────────────────────────────
	if o.Collect != "" {
		if collects != nil {
			if col := collects.Lookup(o.Collect); col != nil {
				if col.Name != "" {
					w("### Collect of the Day: %s (p. %s)", col.Name, o.Collect)
				} else {
					w("### Collect of the Day (p. %s)", o.Collect)
				}
				w("")
				w("%s", col.Text)
				w("")
			} else {
				w("### Collect of the Day (p. %s)", o.Collect)
				w("")
			}
		} else {
			w("### Collect of the Day (p. %s)", o.Collect)
			w("")
		}
	}
}

// psalmDisplay builds the psalm heading string from an Office.
func psalmDisplay(o lectionary.Office) string {
	if len(o.PsalmSets) > 0 {
		groups := make([]string, len(o.PsalmSets))
		for i, set := range o.PsalmSets {
			parts := make([]string, len(set))
			for j, p := range set {
				parts[j] = p.Citation
			}
			s := strings.Join(parts, ", ")
			if set[0].Optional {
				s = "[" + s + "]"
			}
			groups[i] = s
		}
		return strings.Join(groups, " or ")
	}

	if len(o.Psalms) == 0 {
		return "(none)"
	}
	parts := make([]string, len(o.Psalms))
	for i, p := range o.Psalms {
		if p.Optional {
			parts[i] = "(" + p.Citation + ")"
		} else {
			parts[i] = p.Citation
		}
	}
	return strings.Join(parts, ", ")
}

// writeAttribution appends the scripture copyright footer required by the
// API.Bible TOS (Starter plan: visible citation + link to api.bible).
func writeAttribution(b *strings.Builder, bible lectionary.BibleSource) {
	if copyright := bible.Copyright(); copyright != "" {
		fmt.Fprintf(b, "*%s*\n\n", copyright)
	} else {
		fmt.Fprintf(b, "*Scripture: %s*\n\n", bible.Translation())
	}
	if url := bible.AttributionURL(); url != "" {
		fmt.Fprintf(b, "*[api.bible](%s)*\n", url)
	}
}

func officeName(officeType string) string {
	if officeType == "ep" {
		return "Evening Prayer"
	}
	return "Morning Prayer"
}

func selectOffice(day *lectionary.Day, officeType string) lectionary.Office {
	if officeType == "ep" {
		return day.Evening
	}
	return day.Morning
}
