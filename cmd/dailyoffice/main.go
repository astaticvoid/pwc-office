package main

import (
	"flag"
	"fmt"
	"os"
	"time"

	lectionary "github.com/astaticvoid/pwc-office"
	"github.com/astaticvoid/pwc-office/internal/office"
)

func main() {
	flag.Usage = func() {
		fmt.Fprintln(os.Stderr, "usage: dailyoffice [mp|ep] [YYYY-MM-DD]")
	}
	flag.Parse()

	officeType := "mp"
	dateStr := ""
	switch flag.NArg() {
	case 0:
	case 1:
		officeType = flag.Arg(0)
	case 2:
		officeType = flag.Arg(0)
		dateStr = flag.Arg(1)
	default:
		flag.Usage()
		os.Exit(1)
	}

	if officeType != "mp" && officeType != "ep" {
		fmt.Fprintln(os.Stderr, "office must be mp or ep")
		os.Exit(1)
	}

	var d time.Time
	if dateStr == "" {
		d = time.Now()
	} else {
		var err error
		d, err = time.Parse("2006-01-02", dateStr)
		if err != nil {
			fmt.Fprintf(os.Stderr, "invalid date %q: use YYYY-MM-DD\n", dateStr)
			os.Exit(1)
		}
	}

	l, err := lectionary.Load()
	if err != nil {
		fmt.Fprintf(os.Stderr, "loading lectionary: %v\n", err)
		os.Exit(1)
	}

	ps, err := lectionary.LoadPsalter()
	if err != nil {
		fmt.Fprintf(os.Stderr, "loading psalter: %v\n", err)
		os.Exit(1)
	}

	day, err := l.Lookup(d)
	if err != nil {
		fmt.Fprintf(os.Stderr, "%v\n", err)
		os.Exit(1)
	}

	bible, err := lectionary.LoadBible()
	if err != nil {
		fmt.Fprintf(os.Stderr, "loading bible: %v\n", err)
		os.Exit(1)
	}

	collects, err := lectionary.LoadCollects()
	if err != nil {
		fmt.Fprintf(os.Stderr, "loading collects: %v\n", err)
		os.Exit(1)
	}

	forms, err := lectionary.LoadForms()
	if err != nil {
		fmt.Fprintf(os.Stderr, "loading forms: %v\n", err)
		os.Exit(1)
	}

	fmt.Print(office.Render(day, officeType, ps, bible, collects, forms))
}
