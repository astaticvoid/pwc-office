package lectionary

import (
	_ "embed"
	"encoding/json"
	"strings"
	"time"
)

//go:embed data/offices.json
var officesData []byte

// Segment is one typed run of liturgical text within a Form section.
// Type values:
//
//	"leader"   — regular text spoken by the officiant/leader
//	"response" — bold text spoken by the congregation
//	"rubric"   — red italic instructional text (directions, alternative markers, titles)
type Segment struct {
	Type string `json:"type"`
	Text string `json:"text"`
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

// Forms is the loaded collection of all office forms.
type Forms struct {
	data map[string]*Form
}

// LoadForms returns all extracted office forms ready for use.
func LoadForms() (*Forms, error) {
	var raw map[string]*Form
	if err := json.Unmarshal(officesData, &raw); err != nil {
		return nil, err
	}
	return &Forms{data: raw}, nil
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
