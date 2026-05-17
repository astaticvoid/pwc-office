package lectionary

import (
	_ "embed"
	"encoding/json"
	"strings"
	"time"
)

//go:embed data/offices.json
var officesData []byte

// AlternativeGroup is one option within an alternatives block.
type AlternativeGroup struct {
	Label    string    `json:"label"`
	Segments []Segment `json:"segments"`
}

// Segment is one typed run of liturgical text within a Form section.
// Type values:
//
//	"leader"       — regular text spoken by the officiant/leader
//	"response"     — bold text spoken by the congregation
//	"rubric"       — red italic instructional text (directions, titles)
//	"alternatives" — multiple options; Groups holds the named choices
//	"shared"       — reference to a shared block in Forms._shared; Key names it
type Segment struct {
	Type   string             `json:"type"`
	Text   string             `json:"text,omitempty"`
	Groups []AlternativeGroup `json:"groups,omitempty"`
	Key    string             `json:"key,omitempty"`
}

// Form holds the liturgical text for one Daily Office (one season + MP or EP).
// Each content field is a slice of typed Segments preserving the semantic
// structure of the source PDF (leader, response, rubric).
// A nil slice means that section is absent for this office.
type Form struct {
	Title    string `json:"title"`
	Subtitle string `json:"subtitle"`

	// Gathering
	OpeningResponses []Segment `json:"opening_responses"`
	Invitatory       []Segment `json:"invitatory"` // MP in ordinary time only

	// Proclamation
	Responsory  []Segment `json:"responsory"`
	Canticle    []Segment `json:"canticle"`
	Affirmation []Segment `json:"affirmation"`

	// Prayers
	Litany           []Segment `json:"litany"`
	SeasonalCollects []Segment `json:"seasonal_collects"`
	LordsPrayerIntro []Segment `json:"lords_prayer_intro"`

	// Sending
	Dismissal []Segment `json:"dismissal"`
}

// sharedBlock holds the deserialized content of a _shared entry.
type sharedBlock struct {
	Type   string             `json:"type"`
	Groups []AlternativeGroup `json:"groups"`
}

// Forms is the loaded collection of all office forms.
type Forms struct {
	data   map[string]*Form
	shared map[string]*Segment
}

// LoadForms returns all extracted office forms ready for use.
// Shared blocks (doxology, affirmation) are resolved inline so callers
// receive fully expanded Segment slices with no "shared" sentinels.
func LoadForms() (*Forms, error) {
	// Unmarshal into a raw map to extract _shared before populating Forms.
	var raw map[string]json.RawMessage
	if err := json.Unmarshal(officesData, &raw); err != nil {
		return nil, err
	}

	// Parse shared blocks.
	shared := map[string]*Segment{}
	if rawShared, ok := raw["_shared"]; ok {
		var blocks map[string]sharedBlock
		if err := json.Unmarshal(rawShared, &blocks); err != nil {
			return nil, err
		}
		for k, b := range blocks {
			shared[k] = &Segment{Type: b.Type, Groups: b.Groups}
		}
	}

	// Parse individual office forms.
	forms := map[string]*Form{}
	for k, v := range raw {
		if k == "_shared" {
			continue
		}
		var f Form
		if err := json.Unmarshal(v, &f); err != nil {
			return nil, err
		}
		forms[k] = &f
	}

	return &Forms{data: forms, shared: shared}, nil
}

// Resolve expands a "shared" sentinel segment to its full content.
// Returns the segment unchanged if it is not a shared reference.
func (f *Forms) Resolve(seg Segment) Segment {
	if seg.Type == "shared" {
		if s, ok := f.shared[seg.Key]; ok {
			return *s
		}
	}
	return seg
}

// Lookup returns the Form for the given season, office type ("mp" or "ep"),
// and weekday. Weekday is only used when season is OrdinaryTime.
// Returns nil if no form is found.
func (f *Forms) Lookup(season string, officeType string, weekday time.Weekday) *Form {
	key := formKey(season, officeType, weekday)
	return f.data[key]
}

// formKey builds the YAML map key for a given season/office/weekday combination.
func formKey(season, officeType string, weekday time.Weekday) string {
	s := strings.ToLower(season)
	if s == "ordinarytime" {
		s = "ordinary-" + strings.ToLower(weekday.String())
	}
	return s + "-" + officeType
}
