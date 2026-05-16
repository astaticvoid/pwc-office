package lectionary

import (
	"encoding/json"
	"fmt"
	"io/fs"
	"os"
	"strings"
	"sync"
)

// LocalBible reads scripture passages from an fs.FS containing per-book JSON
// files. The FS root must contain files named by canonical book name, e.g.:
//
//	Genesis.json
//	1 Corinthians.json
//	Psalm.json
//
// Each file contains a JSON object: { "chapter": { "verse": "text" } }.
// A nil *LocalBible is valid: Lookup returns "".
type LocalBible struct {
	fsys        fs.FS
	translation string // display name, e.g. "NRSVUE"
	mu          sync.Mutex
	cache       map[string]bibleBook // OSIS code → parsed book
}

// bibleBook maps chapter (1-based) → verse (1-based) → text.
type bibleBook map[int]map[int]string

// LoadLocalBible returns a LocalBible reading from dir.
// name is the display name shown in the attribution footer (e.g. "NRSVUE", "KJV").
// Returns an error only if dir does not exist.
func LoadLocalBible(name, dir string) (*LocalBible, error) {
	if _, err := os.Stat(dir); err != nil {
		return nil, fmt.Errorf("bible data directory %q: %w", dir, err)
	}
	return newLocalBible(strings.ToUpper(name), os.DirFS(dir)), nil
}

// Translation returns the display name of the translation.
func (b *LocalBible) Translation() string {
	if b == nil {
		return ""
	}
	return b.translation
}

// Copyright returns "" — local bibles have no API-supplied copyright string.
func (b *LocalBible) Copyright() string { return "" }

// AttributionURL returns "" — local bibles require no external attribution link.
func (b *LocalBible) AttributionURL() string { return "" }

// Lookup returns formatted text for a scripture citation using the same
// citation syntax accepted by *Bible.Lookup.
func (b *LocalBible) Lookup(citation string) string {
	if b == nil {
		return ""
	}
	if idx := strings.Index(citation, " or "); idx >= 0 {
		citation = citation[:idx]
	}
	citation = strings.TrimSpace(citation)
	if citation == "" {
		return ""
	}

	abbrev, rest, ok := parseAbbrev(citation)
	if !ok {
		return ""
	}
	osisBook, ok := abbrevToOSIS[abbrev]
	if !ok {
		return ""
	}

	// Single-chapter books omit the chapter number (e.g. "Jude 1-16").
	if !strings.Contains(rest, ":") && rest != "" {
		rest = "1:" + rest
	}

	ranges := parseRanges(rest)
	if len(ranges) == 0 {
		return ""
	}

	book := b.getBook(osisBook)
	if book == nil {
		return ""
	}

	var parts []string
	for _, r := range ranges {
		if lines := extractVerses(book, r); len(lines) > 0 {
			parts = append(parts, strings.Join(lines, "\n"))
		}
	}
	return strings.Join(parts, "\n")
}

func (b *LocalBible) getBook(osisCode string) bibleBook {
	b.mu.Lock()
	defer b.mu.Unlock()
	if book, ok := b.cache[osisCode]; ok {
		return book
	}
	book := b.loadBook(osisCode)
	if book != nil {
		b.cache[osisCode] = book
	}
	return book
}

func (b *LocalBible) loadBook(osisCode string) bibleBook {
	filename, ok := osisToBookFile[osisCode]
	if !ok {
		return nil
	}
	data, err := fs.ReadFile(b.fsys, filename+".json")
	if err != nil {
		return nil
	}
	var raw map[string]map[string]string
	if err := json.Unmarshal(data, &raw); err != nil {
		return nil
	}
	book := make(bibleBook, len(raw))
	for chStr, verses := range raw {
		ch, err := parseInt(chStr)
		if err != nil {
			continue
		}
		chMap := make(map[int]string, len(verses))
		for vStr, text := range verses {
			v, err := parseInt(vStr)
			if err != nil {
				continue
			}
			chMap[v] = text
		}
		book[ch] = chMap
	}
	return book
}

func extractVerses(book bibleBook, r verseRange) []string {
	var lines []string
	for ch := r.startCh; ch <= r.endCh; ch++ {
		chData, ok := book[ch]
		if !ok {
			continue
		}
		startV := 1
		if ch == r.startCh {
			startV = r.startV
		}
		endV := maxVerseKey(chData)
		if ch == r.endCh {
			endV = r.endV
		}
		for v := startV; v <= endV; v++ {
			if text, ok := chData[v]; ok {
				lines = append(lines, fmt.Sprintf("%d %s", v, text))
			}
		}
	}
	return lines
}

func maxVerseKey(chData map[int]string) int {
	max := 0
	for k := range chData {
		if k > max {
			max = k
		}
	}
	return max
}

// osisToBookFile maps OSIS book codes to base filenames (without ".json").
var osisToBookFile = map[string]string{
	// Old Testament
	"GEN": "Genesis",
	"EXO": "Exodus",
	"LEV": "Leviticus",
	"NUM": "Numbers",
	"DEU": "Deuteronomy",
	"JOS": "Joshua",
	"JDG": "Judges",
	"RUT": "Ruth",
	"1SA": "1 Samuel",
	"2SA": "2 Samuel",
	"1KI": "1 Kings",
	"2KI": "2 Kings",
	"1CH": "1 Chronicles",
	"2CH": "2 Chronicles",
	"EZR": "Ezra",
	"NEH": "Nehemiah",
	"EST": "Esther",
	"JOB": "Job",
	"PSA": "Psalm",
	"PRO": "Proverbs",
	"ECC": "Ecclesiastes",
	"SNG": "Song Of Songs",
	"ISA": "Isaiah",
	"JER": "Jeremiah",
	"LAM": "Lamentations",
	"EZK": "Ezekiel",
	"DAN": "Daniel",
	"HOS": "Hosea",
	"JOL": "Joel",
	"AMO": "Amos",
	"OBA": "Obadiah",
	"JON": "Jonah",
	"MIC": "Micah",
	"NAH": "Nahum",
	"HAB": "Habakkuk",
	"ZEP": "Zephaniah",
	"HAG": "Haggai",
	"ZEC": "Zechariah",
	"MAL": "Malachi",
	// New Testament
	"MAT": "Matthew",
	"MRK": "Mark",
	"LUK": "Luke",
	"JHN": "John",
	"ACT": "Acts",
	"ROM": "Romans",
	"1CO": "1 Corinthians",
	"2CO": "2 Corinthians",
	"GAL": "Galatians",
	"EPH": "Ephesians",
	"PHP": "Philippians",
	"COL": "Colossians",
	"1TH": "1 Thessalonians",
	"2TH": "2 Thessalonians",
	"1TI": "1 Timothy",
	"2TI": "2 Timothy",
	"TIT": "Titus",
	"PHM": "Philemon",
	"HEB": "Hebrews",
	"JAS": "James",
	"1PE": "1 Peter",
	"2PE": "2 Peter",
	"1JO": "1 John",
	"2JO": "2 John",
	"3JO": "3 John",
	"JUD": "Jude",
	"REV": "Revelation",
	// Apocrypha / Deuterocanon
	"TOB": "Tobit",
	"JDT": "Judith",
	"WIS": "Wisdom Of Solomon",
	"SIR": "Sirach",
	"BAR": "Baruch",
	"1MA": "1 Maccabees",
	"2MA": "2 Maccabees",
	"2ES": "2 Esdras",
}
