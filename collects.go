package lectionary

import (
	_ "embed"
	"encoding/json"
	"regexp"
	"strings"
)

//go:embed data/collects.json
var collectsData []byte

// Collect holds a single BAS collect with its liturgical metadata and prayer text.
type Collect struct {
	Name    string `json:"name"`
	Section string `json:"section"`
	Season  string `json:"season"`
	Proper  int    `json:"proper"`
	Date    string `json:"date"`
	Text    string `json:"text"`
}

// Collects provides collect lookup by BAS page number.
type Collects struct {
	data map[string]*Collect
}

// LoadCollects returns a Collects ready for use.
func LoadCollects() (*Collects, error) {
	var raw map[string]*Collect
	if err := json.Unmarshal(collectsData, &raw); err != nil {
		return nil, err
	}
	return &Collects{data: raw}, nil
}

// Lookup returns the Collect for the given reference string.
// The reference may be a bare page number ("343"), a compound reference
// ("268 (Com: 434 or FAS 361)"), or an or-alternative ("270 or 395 (Ember)").
// The first BAS page number found is used. Returns nil when the page is not
// in the embedded data (e.g. FAS references).
func (c *Collects) Lookup(ref string) *Collect {
	page := extractFirstPage(ref)
	if page == "" {
		return nil
	}
	return c.data[page]
}

// extractFirstPage pulls the first sequence of digits from ref.
var reDigits = regexp.MustCompile(`\d+`)

func extractFirstPage(ref string) string {
	ref = strings.TrimSpace(ref)
	m := reDigits.FindString(ref)
	return m
}
