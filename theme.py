# theme.py — shared color palette and tag color helpers
# Import this in ui.py and launcher.py instead of duplicating constants.

BG           = "#1E1E2E"
HEADER_BG    = "#252537"
WHITE        = "#2A2A3D"
ACCENT       = "#5B5FEF"
ACCENT_HOVER = "#4347C9"
TEXT_DARK    = "#E0E0F0"
TEXT_GRAY    = "#7070A0"
BORDER       = "#3A3A5C"
PIN          = "#F5A623"
PIN_HOVER    = "#E09510"
DANGER       = "#E74C3C"
DANGER_HOVER = "#C0392B"
PINNED_ROW   = "#26263F"

TAG_COLORS = {
    "work":     "#4A90D9",
    "personal": "#7ED321",
    "code":     "#F5A623",
    "other":    "#9B59B6",
    "school":   "#E74C3C",
}
TAG_COLOR_POOL = [
    "#4A90D9","#7ED321","#F5A623","#9B59B6","#E74C3C",
    "#1ABC9C","#E67E22","#3498DB","#E91E63","#00BCD4",
    "#8BC34A","#FF5722","#607D8B","#9C27B0","#FF9800",
]

def get_tag_color(tag):
    if not tag:
        return TEXT_GRAY
    if tag in TAG_COLORS:
        return TAG_COLORS[tag]
    return TAG_COLOR_POOL[sum(ord(c) for c in tag) % len(TAG_COLOR_POOL)]
