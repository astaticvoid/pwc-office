//go:build e2e_smoke || e2e_seasonal

package e2e_test

import (
	"encoding/json"
	"fmt"
	"os/exec"
	"strings"
	"testing"
)


// officeEval is the structured result returned by Claude when evaluating an office.
type officeEval struct {
	Pass              bool     `json:"pass"`
	StructureOK       bool     `json:"structure_ok"`
	SeasonAppropriate bool     `json:"season_appropriate"`
	CasingOK          bool     `json:"casing_ok"`
	ArtifactFree      bool     `json:"artifact_free"`
	Issues            []string `json:"issues"`
}

// evalOffice asks Claude to evaluate rendered office output against liturgical criteria.
// It shells out to the `claude` CLI using the caller's existing Claude Code session —
// no separate API key required.
// or may be nil when official readings are unavailable.
func evalOffice(t *testing.T, date, season, officeType, rendered string, or *officialReadings) officeEval {
	t.Helper()

	if _, err := exec.LookPath("claude"); err != nil {
		t.Skip("claude CLI not found in PATH — install with: npm install -g @anthropic-ai/claude-code")
	}

	officialBlock := ""
	if or != nil {
		officialBlock = fmt.Sprintf(`
Official readings from lectionary.anglican.ca for this day:
- Psalms: %s
- Readings: %s
- Collect page: %s

Verify these specific citations appear correctly in the rendered office. Flag it as an issue if a citation is absent or if the wrong text appears under a citation.`,
			strings.Join(or.Psalms, ", "),
			strings.Join(or.Readings, "; "),
			or.Collect,
		)
	}

	prompt := fmt.Sprintf(`You are evaluating Anglican Daily Office output from a liturgical app (Book of Alternative Services / Pray Without Ceasing, Anglican Church of Canada).

Context:
- Date: %s
- Liturgical season: %s
- Office: %s
%s

Evaluate the office output below. Respond with ONLY a JSON object, no other text:

{
  "pass": true or false,
  "structure_ok": true or false,
  "season_appropriate": true or false,
  "casing_ok": true or false,
  "artifact_free": true or false,
  "issues": ["description of each specific problem found, or empty array if none"]
}

Criteria:
- structure_ok: All required sections present — The Gathering of the Community (opening responses), The Proclamation of the Word (psalm + at least one reading), The Prayers of the Community (litany + seasonal collects + Lord's Prayer), The Sending Forth with dismissal.
- season_appropriate: Liturgical content matches the season. Easter → alleluia/resurrection language in responses; Lent → penitential tone, no alleluia; Advent → waiting/coming of Christ; Christmas → incarnation; Passiontide → passion/cross; Pentecost → Holy Spirit; AllSaints → saints/cloud of witnesses. OrdinaryTime/general Pentecost season can be general. NOTE: The BAS Daily Office lectionary differs from the Sunday Eucharistic lectionary — do not flag readings as wrong simply because they differ from the RCL Sunday propers.
- casing_ok: No capitalization errors — divine titles capitalized (Father, Son, Holy Spirit, Creator when referring to God, God's, Israel); first-person "I" capitalized throughout; sentences start with capital; vocative "O" capitalized (e.g. "Where, O death"); names of people and places capitalized.
- artifact_free: No PDF extraction artifacts — no stray numbers mid-sentence, no garbled words, no running headers embedded in text, no line breaks in wrong places that break word meaning. NOTE: The document always ends with an italic attribution line in the form "*Translation: X*" or a full copyright string — this is intentional and must NOT be flagged as an artifact.
- pass: true only if all four criteria pass.

<office>
%s
</office>`, date, season, officeType, officialBlock, rendered)

	out, err := exec.Command("claude", "-p", prompt).Output()
	if err != nil {
		t.Fatalf("claude CLI failed: %v", err)
	}

	raw := strings.TrimSpace(string(out))
	raw = strings.TrimPrefix(raw, "```json")
	raw = strings.TrimPrefix(raw, "```")
	raw = strings.TrimSuffix(raw, "```")
	raw = strings.TrimSpace(raw)

	var eval officeEval
	if err := json.Unmarshal([]byte(raw), &eval); err != nil {
		t.Fatalf("could not parse Claude response as JSON: %v\nraw: %s", err, raw)
	}
	return eval
}

// reportEval logs the evaluation result and fails the test if it did not pass.
func reportEval(t *testing.T, label string, eval officeEval) {
	t.Helper()
	t.Logf("%s evaluation:", label)
	t.Logf("  structure_ok=%v season_appropriate=%v casing_ok=%v artifact_free=%v",
		eval.StructureOK, eval.SeasonAppropriate, eval.CasingOK, eval.ArtifactFree)
	for _, issue := range eval.Issues {
		t.Logf("  issue: %s", issue)
	}
	if !eval.Pass {
		t.Errorf("%s: office did not pass evaluation (see issues above)", label)
	}
}
