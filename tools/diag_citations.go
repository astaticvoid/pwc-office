//go:build ignore

package main

import (
	"fmt"
	"os"
	"sort"
	"strings"

	lectionary "github.com/astaticvoid/pwc-office"
	"gopkg.in/yaml.v3"
)

type lectItem struct {
	Citation string
	Optional bool
}

func (item *lectItem) UnmarshalYAML(value *yaml.Node) error {
	switch value.Kind {
	case yaml.ScalarNode:
		s := value.Value
		if strings.HasPrefix(s, "(") && strings.HasSuffix(s, ")") {
			item.Citation = s[1 : len(s)-1]
			item.Optional = true
		} else {
			item.Citation = s
		}
	case yaml.MappingNode:
		var m struct {
			Citation string `yaml:"citation"`
			Optional bool   `yaml:"optional"`
		}
		value.Decode(&m)
		item.Citation = m.Citation
		item.Optional = m.Optional
	}
	return nil
}

type diagOffice struct {
	Lessons   []lectItem  `yaml:"lessons"`
	Alternate *diagOffice `yaml:"alternate"`
}

type diagEntry struct {
	Date    string     `yaml:"date"`
	Morning diagOffice `yaml:"morning"`
	Evening diagOffice `yaml:"evening"`
}

type diagDoc struct {
	Entries []diagEntry `yaml:"entries"`
}

func main() {
	data, _ := os.ReadFile("data/lectionary_2026.yaml")
	var d diagDoc
	yaml.Unmarshal(data, &d)

	bible, _ := lectionary.LoadBible()

	type result struct{ date, off, citation string }
	var failures []result
	total := 0

	var check func(date, off string, o diagOffice)
	check = func(date, off string, o diagOffice) {
		for _, l := range o.Lessons {
			c := l.Citation
			if c == "" {
				continue
			}
			total++
			if bible.Lookup(c) == "" {
				failures = append(failures, result{date, off, c})
			}
		}
		if o.Alternate != nil {
			check(date, off+"-alt", *o.Alternate)
		}
	}

	for _, e := range d.Entries {
		check(e.Date, "mp", e.Morning)
		check(e.Date, "ep", e.Evening)
	}

	sort.Slice(failures, func(i, j int) bool { return failures[i].citation < failures[j].citation })

	seen := map[string]bool{}
	fmt.Printf("Total: %d  Failures: %d\n\n", total, len(failures))
	for _, f := range failures {
		if seen[f.citation] {
			continue
		}
		seen[f.citation] = true
		fmt.Printf("  [%s %s] %q\n", f.date, f.off, f.citation)
	}
}
