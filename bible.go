package lectionary

import (
	"embed"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"sync"
	"unicode"
)

//go:embed data/bible
var bibleFS embed.FS

// Bible provides passage lookup from the embedded NRSVUE text.
// Books are loaded on first access and cached.
type Bible struct {
	mu    sync.Mutex
	cache map[string]bibleBook // keyed by canonical book name
}

// bibleBook maps chapter (1-based int) → verse (1-based int) → text.
type bibleBook map[int]map[int]string

// LoadBible returns a Bible ready for citation lookups.
func LoadBible() (*Bible, error) {
	return &Bible{cache: make(map[string]bibleBook)}, nil
}

// Lookup returns the formatted text for a scripture citation.
// Returns empty string when the citation cannot be resolved.
// Supported forms (all as they appear in the BAS/PWC lectionary):
//
//	"Dan 7:9-14"
//	"Dt 9:23—10:5"          (em-dash cross-chapter range)
//	"Ezek 1:1-14, 24-28b"   (comma-separated ranges, letter suffixes)
//	"Am 1:1-5, 13—2:8"      (mixed within- and cross-chapter)
//	"1 Sam 12:1-6, 16-25"   (numbered book)
//	"Lk 15:1-2, 11-32"
//
// For "A or B" alternatives the first option is used.
// Parenthetical verse segments such as (29) are included.
func (b *Bible) Lookup(citation string) string {
	// "A or B" → use first.
	if idx := strings.Index(citation, " or "); idx >= 0 {
		citation = citation[:idx]
	}
	citation = strings.TrimSpace(citation)

	// Parse book name and remainder.
	bookName, rest, ok := parseBookName(citation)
	if !ok {
		return ""
	}

	book, err := b.loadBook(bookName)
	if err != nil {
		return ""
	}

	// Single-chapter books omit the chapter number (e.g. "Jude 1-16").
	// Prepend "1:" so the range parser has a chapter reference.
	if !strings.Contains(rest, ":") && rest != "" {
		rest = "1:" + rest
	}

	segments := parseRanges(rest)
	if len(segments) == 0 {
		return ""
	}

	var lines []string
	for _, seg := range segments {
		for ch := seg.startCh; ch <= seg.endCh; ch++ {
			chData, ok := book[ch]
			if !ok {
				continue
			}
			startV, endV := 1, maxVerseInChapter(chData)
			if ch == seg.startCh {
				startV = seg.startV
			}
			if ch == seg.endCh {
				endV = seg.endV
			}
			for v := startV; v <= endV; v++ {
				if text, ok := chData[v]; ok {
					lines = append(lines, fmt.Sprintf("%d %s", v, text))
				}
			}
		}
	}
	return strings.Join(lines, "\n")
}

// ── Internal types ─────────────────────────────────────────────────────────────

type verseRange struct {
	startCh, endCh int
	startV, endV   int
}

// ── Book loading ───────────────────────────────────────────────────────────────

func (b *Bible) loadBook(name string) (bibleBook, error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	if bk, ok := b.cache[name]; ok {
		return bk, nil
	}
	data, err := bibleFS.ReadFile("data/bible/" + name + ".json")
	if err != nil {
		return nil, err
	}
	// JSON has string keys; unmarshal to map[string]map[string]string then convert.
	var raw map[string]map[string]string
	if err := json.Unmarshal(data, &raw); err != nil {
		return nil, err
	}
	bk := make(bibleBook, len(raw))
	for chStr, verses := range raw {
		ch, err := strconv.Atoi(chStr)
		if err != nil {
			continue
		}
		bk[ch] = make(map[int]string, len(verses))
		for vStr, text := range verses {
			v, err := strconv.Atoi(vStr)
			if err != nil {
				continue
			}
			bk[ch][v] = text
		}
	}
	b.cache[name] = bk
	return bk, nil
}

func maxVerseInChapter(ch map[int]string) int {
	max := 0
	for v := range ch {
		if v > max {
			max = v
		}
	}
	return max
}

// ── Citation parser ────────────────────────────────────────────────────────────

// parseBookName splits "Dan 7:9-14" into ("Daniel", "7:9-14", true).
// Handles numbered books ("1 Sam", "2 Chr") and plain names ("Jn", "Acts").
func parseBookName(citation string) (canonical, rest string, ok bool) {
	// Strip a leading optional block: "(2 Kgs 1:1), Mt 1:1" → keep "Mt 1:1".
	if strings.HasPrefix(citation, "(") {
		if end := strings.Index(citation, "), "); end >= 0 {
			citation = strings.TrimSpace(citation[end+2:])
		}
	}

	// A book may start with a digit and space: "1 Sam", "2 Chr".
	s := citation
	prefix := ""
	if len(s) > 0 && s[0] >= '1' && s[0] <= '4' && len(s) > 1 && s[1] == ' ' {
		prefix = string(s[0]) + " "
		s = s[2:]
	}

	// Collect alphabetic book-name characters (may include spaces for multi-word names).
	// Stop at the chapter number.
	abbrev := ""
	for i, r := range s {
		if unicode.IsDigit(r) || r == ':' {
			rest = strings.TrimSpace(s[i:])
			break
		}
		abbrev += string(r)
	}
	if abbrev == "" {
		return "", "", false
	}
	abbrev = strings.TrimSpace(prefix + strings.TrimSpace(abbrev))

	canonical, ok = abbrevToBook[abbrev]
	return canonical, rest, ok
}

// parseRanges converts the chapter:verse portion of a citation into a slice
// of verseRange structs. Handles:
//   - "7:9-14"           single range
//   - "1:1-14, 24-28"    two ranges same chapter
//   - "9:23—10:5"        cross-chapter em-dash
//   - "1:1-5, 13—2:8"    mixed within- and cross-chapter
//   - "16:18-20, 17:14"  ranges in different chapters
func parseRanges(s string) []verseRange {
	// Normalise: em-dash → §, so we can split on it unambiguously.
	s = strings.ReplaceAll(s, "—", "§")

	// Split on § to identify cross-chapter boundaries.
	// Each segment is either "ch:v-v, v-v" or "ch:v".
	parts := strings.Split(s, "§")

	var result []verseRange
	currentCh := 0 // chapter context carried across commas

	for pi, part := range parts {
		part = strings.TrimSpace(part)

		// Each part may contain comma-separated sub-ranges.
		subParts := strings.Split(part, ",")

		for si, sub := range subParts {
			sub = strings.TrimSpace(sub)
			if sub == "" {
				continue
			}
			// Strip parentheses — treat optional verses as included.
			sub = strings.Trim(sub, "()")

			// Does this sub-part contain a chapter reference (":")?
			if idx := strings.Index(sub, ":"); idx >= 0 {
				chStr := sub[:idx]
				ch, err := strconv.Atoi(chStr)
				if err != nil {
					continue
				}
				currentCh = ch
				sub = sub[idx+1:]
			}

			if currentCh == 0 {
				continue
			}

			// Last sub-part of a non-final § segment may have a cross-chapter
			// em-dash continuation in the next § segment.
			isCrossChapterStart := pi < len(parts)-1 && si == len(subParts)-1

			startV, endV := parseVerseRange(sub)
			if startV == 0 {
				continue
			}

			if isCrossChapterStart {
				// This verse is the start of a cross-chapter range.
				// The end is parsed from the next § segment.
				nextPart := strings.TrimSpace(parts[pi+1])
				// nextPart may be "10:5" or just "5".
				endCh, endVerse := parseChapterVerse(nextPart, currentCh)
				result = append(result, verseRange{
					startCh: currentCh, startV: startV,
					endCh: endCh, endV: endVerse,
				})
				// Skip the next § part's leading reference since we consumed it.
				// Remaining sub-parts of the next part (after comma) still apply.
				// We handle this by marking the next § segment's first sub-part consumed.
				parts[pi+1] = consumeLeadingRef(parts[pi+1])
				currentCh = endCh
			} else {
				result = append(result, verseRange{
					startCh: currentCh, startV: startV,
					endCh: currentCh, endV: endV,
				})
			}
		}
	}
	return result
}

// parseVerseRange parses "9-14", "28b", "9" into (start, end).
// Letter suffixes (a, b, c) are stripped. Returns (0,0) on error.
func parseVerseRange(s string) (start, end int) {
	s = strings.TrimSpace(s)
	if idx := strings.Index(s, "-"); idx >= 0 {
		a := parseVerseNum(s[:idx])
		b := parseVerseNum(s[idx+1:])
		return a, b
	}
	v := parseVerseNum(s)
	return v, v
}

func parseVerseNum(s string) int {
	s = strings.TrimSpace(s)
	// Strip trailing letter suffix.
	for len(s) > 0 && (s[len(s)-1] == 'a' || s[len(s)-1] == 'b' || s[len(s)-1] == 'c') {
		s = s[:len(s)-1]
	}
	n, _ := strconv.Atoi(s)
	return n
}

// parseChapterVerse parses "10:5" → (10, 5) or "5" → (defaultCh, 5).
func parseChapterVerse(s string, defaultCh int) (ch, v int) {
	s = strings.TrimSpace(s)
	// Take only the first comma-separated segment.
	if idx := strings.Index(s, ","); idx >= 0 {
		s = strings.TrimSpace(s[:idx])
	}
	if idx := strings.Index(s, ":"); idx >= 0 {
		ch, _ = strconv.Atoi(s[:idx])
		v = parseVerseNum(s[idx+1:])
		return ch, v
	}
	return defaultCh, parseVerseNum(s)
}

// consumeLeadingRef removes the first "ch:v" or "v" token from s (up to comma or end).
func consumeLeadingRef(s string) string {
	s = strings.TrimSpace(s)
	if idx := strings.Index(s, ","); idx >= 0 {
		return strings.TrimSpace(s[idx+1:])
	}
	return ""
}

// ── Abbreviation map ───────────────────────────────────────────────────────────

// abbrevToBook maps BAS/PWC lectionary abbreviations to the canonical book
// names used as filenames in data/bible/.
var abbrevToBook = map[string]string{
	// Old Testament
	"Gen":    "Genesis",
	"Ex":     "Exodus",
	"Lev":    "Leviticus",
	"Num":    "Numbers",
	"Dt":     "Deuteronomy",
	"Jos":    "Joshua",
	"Jg":     "Judges",
	"Ruth":   "Ruth",
	"1 Sam":  "1 Samuel",
	"2 Sam":  "2 Samuel",
	"1 Kgs":  "1 Kings",
	"2 Kgs":  "2 Kings",
	"1 Chr":  "1 Chronicles",
	"2 Chr":  "2 Chronicles",
	"Ezra":   "Ezra",
	"Neh":    "Nehemiah",
	"Est":    "Esther",
	"Job":    "Job",
	"Ps":     "Psalm",
	"Pr":     "Proverbs",
	"Ec":     "Ecclesiastes",
	"Song":   "Song Of Songs",
	"Is":     "Isaiah",
	"Jer":    "Jeremiah",
	"Lam":    "Lamentations",
	"Ezek":   "Ezekiel",
	"Dan":    "Daniel",
	"Hos":    "Hosea",
	"Jl":     "Joel",
	"Am":     "Amos",
	"Ob":     "Obadiah",
	"Jon":    "Jonah",
	"Mic":    "Micah",
	"Nah":    "Nahum",
	"Hab":    "Habakkuk",
	"Zeph":   "Zephaniah",
	"Hag":    "Haggai",
	"Zech":   "Zechariah",
	"Mal":    "Malachi",
	// New Testament
	"Mt":     "Matthew",
	"Mk":     "Mark",
	"Lk":     "Luke",
	"Jn":     "John",
	"Acts":   "Acts",
	"Rom":    "Romans",
	"1 Cor":  "1 Corinthians",
	"2 Cor":  "2 Corinthians",
	"Gal":    "Galatians",
	"Eph":    "Ephesians",
	"Phil":   "Philippians",
	"Col":    "Colossians",
	"1 Th":   "1 Thessalonians",
	"2 Th":   "2 Thessalonians",
	"1 Tim":  "1 Timothy",
	"2 Tim":  "2 Timothy",
	"Tit":    "Titus",
	"Philem": "Philemon",
	"Heb":    "Hebrews",
	"Jas":    "James",
	"1 Pet":  "1 Peter",
	"2 Pet":  "2 Peter",
	"1 Jn":   "1 John",
	"2 Jn":   "2 John",
	"3 Jn":   "3 John",
	"Jude":   "Jude",
	"Rev":    "Revelation",
	// Apocrypha / Deuterocanon
	"Tob":    "Tobit",
	"Jdt":    "Judith",
	"Wis":    "Wisdom Of Solomon",
	"Sir":    "Sirach",
	"Bar":    "Baruch",
	"1 Macc": "1 Maccabees",
	"2 Macc": "2 Maccabees",
	"2 Esd":  "2 Esdras",
}
