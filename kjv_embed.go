package lectionary

import (
	"embed"
	"io/fs"
)

//go:embed data/translations/kjv
var kjvFS embed.FS

// KJV returns a LocalBible backed by the embedded KJV 1769 data (with Apocrypha).
// It requires no external files and works out of the box.
func KJV() *LocalBible {
	sub, _ := fs.Sub(kjvFS, "data/translations/kjv")
	return newLocalBible("KJV", sub)
}

// newLocalBible creates a LocalBible from any fs.FS (used by KJV and LoadLocalBible).
func newLocalBible(name string, fsys fs.FS) *LocalBible {
	return &LocalBible{
		fsys:        fsys,
		translation: name,
		cache:       make(map[string]bibleBook),
	}
}
