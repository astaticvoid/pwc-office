package lectionary

import (
	_ "embed"
	"encoding/json"
	"fmt"
	"regexp"
	"strconv"
	"strings"
)

//go:embed data/psalter.json
var psalterData []byte

// Psalter holds all 150 psalm texts indexed by psalm number.
type Psalter struct {
	psalms map[int]*psalterEntry
}

type psalterEntry struct {
	Number int    `json:"number"`
	Book   int    `json:"book"`
	Title  string `json:"title"`
	Text   string `json:"text"`
}

// LoadPsalter parses the embedded Liturgical Psalter JSON file.
func LoadPsalter() (*Psalter, error) {
	var raw map[string]*psalterEntry
	if err := json.Unmarshal(psalterData, &raw); err != nil {
		return nil, fmt.Errorf("psalter: parsing psalter.json: %w", err)
	}
	p := &Psalter{psalms: make(map[int]*psalterEntry, len(raw))}
	for _, ps := range raw {
		p.psalms[ps.Number] = ps
	}
	return p, nil
}

var reInvitatory = regexp.MustCompile(`(?i)\s*\(invitatory\)`)

// Lookup returns the psalm text for a citation string.
// Supported forms:
//
//	"8"               — full Psalm 8
//	"119:1-24"        — Psalm 119 verses 1–24
//	"95 (Invitatory)" — Psalm 95 full text, invitatory suffix ignored
//
// Returns an empty string when the citation cannot be resolved.
func (p *Psalter) Lookup(citation string) string {
	cit := strings.TrimSpace(reInvitatory.ReplaceAllString(citation, ""))

	var psalmNum, startVerse, endVerse int

	if idx := strings.Index(cit, ":"); idx >= 0 {
		n, err := strconv.Atoi(strings.TrimSpace(cit[:idx]))
		if err != nil {
			return ""
		}
		psalmNum = n
		startVerse, endVerse = psalterParseRange(cit[idx+1:])
	} else {
		if strings.Contains(cit, "-") {
			// Bare range without psalm number — unresolvable without context.
			return ""
		}
		n, err := strconv.Atoi(strings.TrimSpace(cit))
		if err != nil {
			return ""
		}
		psalmNum = n
	}

	ps, ok := p.psalms[psalmNum]
	if !ok {
		return ""
	}
	if startVerse == 0 {
		return ps.Text
	}
	return psalterExtractVerses(ps.Text, startVerse, endVerse)
}

// LookupNumber returns the full text of a psalm by number.
func (p *Psalter) LookupNumber(n int) string {
	ps, ok := p.psalms[n]
	if !ok {
		return ""
	}
	return ps.Text
}

func psalterParseRange(s string) (start, end int) {
	s = strings.TrimSpace(s)
	if idx := strings.Index(s, "-"); idx >= 0 {
		a, err1 := strconv.Atoi(strings.TrimSpace(s[:idx]))
		b, err2 := strconv.Atoi(strings.TrimSpace(s[idx+1:]))
		if err1 != nil || err2 != nil {
			return 0, 0
		}
		return a, b
	}
	a, err := strconv.Atoi(s)
	if err != nil {
		return 0, 0
	}
	return a, a
}

var reVerseNum = regexp.MustCompile(`^(\d+)\s`)

// psalterExtractVerses returns lines for verses start..end (inclusive).
// Section headings (Aleph, Part I, etc.) are included when they precede an in-range verse.
func psalterExtractVerses(text string, start, end int) string {
	lines := strings.Split(text, "\n")
	var out []string
	inRange := false
	pendingSection := ""

	for _, line := range lines {
		m := reVerseNum.FindStringSubmatch(line)
		if m != nil {
			vNum, _ := strconv.Atoi(m[1])
			if vNum >= start && vNum <= end {
				if !inRange && pendingSection != "" {
					out = append(out, pendingSection)
				}
				pendingSection = ""
				inRange = true
				out = append(out, line)
			} else {
				if inRange {
					break
				}
				pendingSection = ""
				inRange = false
			}
			continue
		}

		if inRange {
			out = append(out, line)
		} else {
			stripped := strings.TrimSpace(line)
			if stripped != "" && !strings.HasPrefix(line, " ") {
				pendingSection = line
			} else {
				pendingSection = ""
			}
		}
	}

	return strings.Join(out, "\n")
}
