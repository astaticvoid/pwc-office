package lectionary

import (
	_ "embed"
	"strings"
	"time"

	"gopkg.in/yaml.v3"
)

//go:embed data/offices.yaml
var officesData []byte

// Segment is one typed run of liturgical text within a Form section.
// Type values:
//
//	"leader"   — regular text spoken by the officiant/leader
//	"response" — bold text spoken by the congregation
//	"rubric"   — red italic instructional text (directions, alternative markers, titles)
type Segment struct {
	Type string `yaml:"type"`
	Text string `yaml:"text"`
}

// Form holds the liturgical text for one Daily Office (one season + MP or EP).
// Each content field is a slice of typed Segments preserving the semantic
// structure of the source PDF (leader, response, rubric).
// A nil slice means that section is absent for this office.
type Form struct {
	Title    string `yaml:"title"`
	Subtitle string `yaml:"subtitle"`

	// Gathering
	OpeningResponses []Segment `yaml:"opening_responses"`
	Invitatory       []Segment `yaml:"invitatory"` // MP in ordinary time only

	// Proclamation
	Responsory  []Segment `yaml:"responsory"`
	Canticle    []Segment `yaml:"canticle"`
	Affirmation []Segment `yaml:"affirmation"`

	// Prayers
	Litany           []Segment `yaml:"litany"`
	SeasonalCollects []Segment `yaml:"seasonal_collects"`
	LordsPrayerIntro []Segment `yaml:"lords_prayer_intro"`

	// Sending
	Dismissal []Segment `yaml:"dismissal"`
}

// Forms is the loaded collection of all office forms.
type Forms struct {
	data map[string]*Form
}

// LoadForms returns all extracted office forms ready for use.
func LoadForms() (*Forms, error) {
	var raw map[string]*Form
	if err := yaml.Unmarshal(officesData, &raw); err != nil {
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
