//go:build ignore

package main

import (
	"fmt"
	"os"
	"sort"

	lectionary "github.com/astaticvoid/pwc-office"
)

func main() {
	l, err := lectionary.Load()
	if err != nil {
		fmt.Println("load:", err)
		return
	}
	bible, err := lectionary.LoadBible(os.Getenv("BIBLE_API_KEY"))
	if err != nil {
		fmt.Println("bible:", err)
		return
	}

	type result struct{ date, off, citation string }
	var failures []result
	total := 0

	var checkOffice func(date, off string, o lectionary.Office)
	checkOffice = func(date, off string, o lectionary.Office) {
		for _, lesson := range o.Lessons {
			c := lesson.Citation
			if c == "" {
				continue
			}
			total++
			if bible.Lookup(c) == "" {
				failures = append(failures, result{date, off, c})
			}
		}
		if o.Alternate != nil {
			checkOffice(date, off+"-alt", *o.Alternate)
		}
	}

	for _, day := range l.AllDays() {
		date := day.Date.Format("2006-01-02")
		checkOffice(date, "mp", day.Morning)
		checkOffice(date, "ep", day.Evening)
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
