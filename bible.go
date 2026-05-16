package lectionary

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
	"unicode"
)

// BibleSource is the interface satisfied by both the API.Bible client (*Bible)
// and the local JSON reader (*LocalBible). A nil BibleSource is valid: the
// office renderer skips scripture text when none is provided.
type BibleSource interface {
	Lookup(citation string) string
	Translation() string
	Copyright() string
	// AttributionURL returns a URL to display alongside the copyright notice,
	// or "" if no external attribution link is required.
	AttributionURL() string
}

const (
	bibleBaseURL = "https://rest.api.bible/v1"
	cacheMaxAge  = 30 * 24 * time.Hour
)

// kjvBibleID is the API.Bible ID for the King James (Authorised) Version with
// Apocrypha (-01), which covers the full Anglican Daily Office lectionary
// including deuterocanonical readings.
const kjvBibleID = "de4e12af7f28f599-01"

// Bible provides passage lookup via the API.Bible REST API with disk caching.
// A nil *Bible is valid: Lookup returns "" and the renderer skips scripture text.
type Bible struct {
	apiKey    string
	bibleID   string
	cacheDir  string
	copyright string
	client    *http.Client
	mu        sync.Mutex
}

// LoadBible returns a Bible client ready for KJV passage lookups.
// Returns nil without error when apiKey is empty — the renderer skips scripture text.
func LoadBible(apiKey string) (*Bible, error) {
	if apiKey == "" {
		return nil, nil
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return nil, fmt.Errorf("bible: home dir: %w", err)
	}
	cacheDir := filepath.Join(home, ".cache", "pwc_office", "bible", kjvBibleID)
	if err := os.MkdirAll(cacheDir, 0700); err != nil {
		return nil, fmt.Errorf("bible: creating cache dir: %w", err)
	}
	return &Bible{
		apiKey:   apiKey,
		bibleID:  kjvBibleID,
		cacheDir: cacheDir,
		client:   &http.Client{Timeout: 30 * time.Second},
	}, nil
}

// Translation returns "KJV".
func (b *Bible) Translation() string {
	if b == nil {
		return ""
	}
	return "KJV"
}

// AttributionURL returns the API.Bible homepage URL for TOS attribution.
func (b *Bible) AttributionURL() string {
	if b == nil {
		return ""
	}
	return "https://api.bible"
}

// Copyright returns the copyright string for the current translation.
// Empty until the first successful passage fetch.
func (b *Bible) Copyright() string {
	if b == nil {
		return ""
	}
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.copyright
}

// Lookup returns the formatted text for a scripture citation.
// Returns empty string when the citation cannot be resolved.
// Supported forms match the BAS/PWC lectionary:
//
//	"Dan 7:9-14"
//	"Dt 9:23—10:5"          (em-dash cross-chapter range)
//	"Ezek 1:1-14, 24-28b"  (comma-separated ranges)
//	"Jude 1-16"             (single-chapter book)
//
// For "A or B" alternatives the first option is used.
func (b *Bible) Lookup(citation string) string {
	if b == nil {
		return ""
	}
	// "A or B" → use first.
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

	var parts []string
	for _, r := range ranges {
		passageID := rangeToOSIS(osisBook, r)
		if text := b.lookupPassage(passageID); text != "" {
			parts = append(parts, text)
		}
	}
	return strings.Join(parts, "\n")
}

// ── Internal ───────────────────────────────────────────────────────────────────

type cachedEntry struct {
	Text      string    `json:"text"`
	Copyright string    `json:"copyright"`
	FetchedAt time.Time `json:"fetched_at"`
}

func (b *Bible) lookupPassage(passageID string) string {
	if cached := b.readCache(passageID); cached != "" {
		return cached
	}
	text, copyright, err := b.fetchFromAPI(passageID)
	if err != nil {
		return ""
	}
	b.mu.Lock()
	if copyright != "" && b.copyright == "" {
		b.copyright = copyright
	}
	b.mu.Unlock()
	b.writeCache(passageID, text)
	return text
}

func (b *Bible) cacheFile(passageID string) string {
	safe := strings.NewReplacer(".", "_", "/", "_").Replace(passageID)
	return filepath.Join(b.cacheDir, safe+".json")
}

func (b *Bible) readCache(passageID string) string {
	data, err := os.ReadFile(b.cacheFile(passageID))
	if err != nil {
		return ""
	}
	var entry cachedEntry
	if err := json.Unmarshal(data, &entry); err != nil {
		return ""
	}
	if time.Since(entry.FetchedAt) > cacheMaxAge {
		return ""
	}
	b.mu.Lock()
	if entry.Copyright != "" && b.copyright == "" {
		b.copyright = entry.Copyright
	}
	b.mu.Unlock()
	return entry.Text
}

func (b *Bible) writeCache(passageID, text string) {
	b.mu.Lock()
	copyright := b.copyright
	b.mu.Unlock()
	entry := cachedEntry{
		Text:      text,
		Copyright: copyright,
		FetchedAt: time.Now().UTC(),
	}
	data, err := json.Marshal(entry)
	if err != nil {
		return
	}
	_ = os.WriteFile(b.cacheFile(passageID), data, 0600)
}

func (b *Bible) fetchFromAPI(passageID string) (text, copyright string, err error) {
	url := fmt.Sprintf(
		"%s/bibles/%s/passages/%s?content-type=text&include-verse-numbers=true&include-titles=false&include-chapter-numbers=false",
		bibleBaseURL, b.bibleID, passageID,
	)
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return "", "", err
	}
	req.Header.Set("api-key", b.apiKey)

	resp, err := b.client.Do(req)
	if err != nil {
		return "", "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return "", "", fmt.Errorf("bible API %s: status %d", passageID, resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", "", err
	}

	var result struct {
		Data struct {
			Content   string `json:"content"`
			Copyright string `json:"copyright"`
		} `json:"data"`
	}
	if err := json.Unmarshal(body, &result); err != nil {
		return "", "", err
	}

	return normalizePassageText(result.Data.Content), result.Data.Copyright, nil
}

// normalizePassageText converts API text to our output format.
// Lines starting with "[N]" are rewritten to "N text" to match test expectations.
// Leading/trailing whitespace is stripped; blank lines are removed.
func normalizePassageText(s string) string {
	lines := strings.Split(strings.TrimSpace(s), "\n")
	var out []string
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		// Convert leading "[N]" to "N ".
		if strings.HasPrefix(line, "[") {
			if end := strings.Index(line, "]"); end > 0 {
				num := line[1:end]
				rest := strings.TrimSpace(line[end+1:])
				line = num + " " + rest
			}
		}
		line = stripSuperscripts(line)
		out = append(out, line)
	}
	return strings.Join(out, "\n")
}

func stripSuperscripts(s string) string {
	var b strings.Builder
	for _, r := range s {
		if r >= '⁰' && r <= '⁹' {
			continue
		}
		b.WriteRune(r)
	}
	return b.String()
}

// rangeToOSIS converts a verseRange to an API.Bible passage ID string.
func rangeToOSIS(osisBook string, r verseRange) string {
	start := fmt.Sprintf("%s.%d.%d", osisBook, r.startCh, r.startV)
	end := fmt.Sprintf("%s.%d.%d", osisBook, r.endCh, r.endV)
	if start == end {
		return start
	}
	return start + "-" + end
}

// parseAbbrev splits "Dan 7:9-14" into ("Dan", "7:9-14", true).
// The returned abbreviation is the raw BAS/PWC abbreviation (e.g. "Dan", "1 Sam").
func parseAbbrev(citation string) (abbrev, rest string, ok bool) {
	// Strip a leading optional block: "(2 Kgs 1:1), Mt 1:1" → "Mt 1:1".
	if strings.HasPrefix(citation, "(") {
		if end := strings.Index(citation, "), "); end >= 0 {
			citation = strings.TrimSpace(citation[end+2:])
		}
	}

	s := citation
	prefix := ""
	if len(s) > 0 && s[0] >= '1' && s[0] <= '4' && len(s) > 1 && s[1] == ' ' {
		prefix = string(s[0]) + " "
		s = s[2:]
	}

	nameStr := ""
	for i, r := range s {
		if unicode.IsDigit(r) || r == ':' {
			rest = strings.TrimSpace(s[i:])
			break
		}
		nameStr += string(r)
	}
	if nameStr == "" {
		return "", "", false
	}
	abbrev = strings.TrimSpace(prefix + strings.TrimSpace(nameStr))
	_, ok = abbrevToOSIS[abbrev]
	return abbrev, rest, ok
}

// ── Abbreviation → OSIS book code ─────────────────────────────────────────────

var abbrevToOSIS = map[string]string{
	// Old Testament
	"Gen":    "GEN",
	"Ex":     "EXO",
	"Lev":    "LEV",
	"Num":    "NUM",
	"Dt":     "DEU",
	"Jos":    "JOS",
	"Jg":     "JDG",
	"Ruth":   "RUT",
	"1 Sam":  "1SA",
	"2 Sam":  "2SA",
	"1 Kgs":  "1KI",
	"2 Kgs":  "2KI",
	"1 Chr":  "1CH",
	"2 Chr":  "2CH",
	"Ezra":   "EZR",
	"Neh":    "NEH",
	"Est":    "EST",
	"Job":    "JOB",
	"Ps":     "PSA",
	"Pr":     "PRO",
	"Ec":     "ECC",
	"Song":   "SNG",
	"Is":     "ISA",
	"Jer":    "JER",
	"Lam":    "LAM",
	"Ezek":   "EZK",
	"Dan":    "DAN",
	"Hos":    "HOS",
	"Jl":     "JOL",
	"Am":     "AMO",
	"Ob":     "OBA",
	"Jon":    "JON",
	"Mic":    "MIC",
	"Nah":    "NAH",
	"Hab":    "HAB",
	"Zeph":   "ZEP",
	"Hag":    "HAG",
	"Zech":   "ZEC",
	"Mal":    "MAL",
	// New Testament
	"Mt":     "MAT",
	"Mk":     "MRK",
	"Lk":     "LUK",
	"Jn":     "JHN",
	"Acts":   "ACT",
	"Rom":    "ROM",
	"1 Cor":  "1CO",
	"2 Cor":  "2CO",
	"Gal":    "GAL",
	"Eph":    "EPH",
	"Phil":   "PHP",
	"Col":    "COL",
	"1 Th":   "1TH",
	"2 Th":   "2TH",
	"1 Tim":  "1TI",
	"2 Tim":  "2TI",
	"Tit":    "TIT",
	"Philem": "PHM",
	"Heb":    "HEB",
	"Jas":    "JAS",
	"1 Pet":  "1PE",
	"2 Pet":  "2PE",
	"1 Jn":   "1JO",
	"2 Jn":   "2JO",
	"3 Jn":   "3JO",
	"Jude":   "JUD",
	"Rev":    "REV",
	// Apocrypha / Deuterocanon (NIV does not include these; GNT and KJV may)
	"Tob":    "TOB",
	"Jdt":    "JDT",
	"Wis":    "WIS",
	"Sir":    "SIR",
	"Bar":    "BAR",
	"1 Macc": "1MA",
	"2 Macc": "2MA",
	"2 Esd":  "2ES",
}

// ── Citation parser (retained from embedded implementation) ────────────────────

type verseRange struct {
	startCh, endCh int
	startV, endV   int
}

func parseRanges(s string) []verseRange {
	s = strings.ReplaceAll(s, "—", "§")
	parts := strings.Split(s, "§")
	var result []verseRange
	currentCh := 0

	for pi, part := range parts {
		part = strings.TrimSpace(part)
		subParts := strings.Split(part, ",")

		for si, sub := range subParts {
			sub = strings.TrimSpace(sub)
			if sub == "" {
				continue
			}
			sub = strings.Trim(sub, "()")

			if idx := strings.Index(sub, ":"); idx >= 0 {
				ch, err := parseInt(sub[:idx])
				if err != nil {
					continue
				}
				currentCh = ch
				sub = sub[idx+1:]
			}
			if currentCh == 0 {
				continue
			}

			isCrossChapterStart := pi < len(parts)-1 && si == len(subParts)-1
			startV, endV := parseVerseRange(sub)
			if startV == 0 {
				continue
			}

			if isCrossChapterStart {
				nextPart := strings.TrimSpace(parts[pi+1])
				endCh, endVerse := parseChapterVerse(nextPart, currentCh)
				result = append(result, verseRange{
					startCh: currentCh, startV: startV,
					endCh: endCh, endV: endVerse,
				})
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
	for len(s) > 0 && (s[len(s)-1] == 'a' || s[len(s)-1] == 'b' || s[len(s)-1] == 'c') {
		s = s[:len(s)-1]
	}
	n, _ := parseInt(s)
	return n
}

func parseChapterVerse(s string, defaultCh int) (ch, v int) {
	s = strings.TrimSpace(s)
	if idx := strings.Index(s, ","); idx >= 0 {
		s = strings.TrimSpace(s[:idx])
	}
	if idx := strings.Index(s, ":"); idx >= 0 {
		ch, _ = parseInt(s[:idx])
		v = parseVerseNum(s[idx+1:])
		return ch, v
	}
	return defaultCh, parseVerseNum(s)
}

func consumeLeadingRef(s string) string {
	s = strings.TrimSpace(s)
	if idx := strings.Index(s, ","); idx >= 0 {
		return strings.TrimSpace(s[idx+1:])
	}
	return ""
}

func parseInt(s string) (int, error) {
	s = strings.TrimSpace(s)
	n := 0
	for _, c := range s {
		if c < '0' || c > '9' {
			return 0, fmt.Errorf("not a number: %q", s)
		}
		n = n*10 + int(c-'0')
	}
	if s == "" {
		return 0, fmt.Errorf("empty")
	}
	return n, nil
}
