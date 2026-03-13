"""Bot message templates for the conversation flow."""

WELCOME_MSG = (
    "*Hey there! I'm PulseUP — your NYC kids event finder.* ✨\n\n"
    "Tell me a bit about your family and I'll find the best events for you. "
    "This takes about 1 minute."
)

Q1_CHILDREN_MSG = (
    "How many kids do you have, and how old are they?\n\n"
    "For example: \"2 kids, ages 3 and 6\" or \"a 4-year-old daughter\""
)

Q2_INTERESTS_MSG = "*What kinds of activities do your kids enjoy?*"

Q2_INTERESTS_OPTIONS = [
    {"id": "active", "title": "⚽ Active"},
    {"id": "creative", "title": "🎨 Creative"},
    {"id": "educational", "title": "🧪 Educational"},
    {"id": "shows", "title": "🎭 Shows & Performances"},
    {"id": "outdoor", "title": "🌳 Outdoor / Nature"},
    {"id": "fun_play", "title": "🎮 Fun & Play"},
    {"id": "adventure", "title": "🚀 Adventure"},
    {"id": "books", "title": "📚 Books & Storytime"},
    {"id": "social", "title": "👶 Social / Playdates"},
]

Q2_PER_CHILD_MSG = "What does your *{age}-year-old* enjoy?"
Q2_SUMMARY_MSG = "Here's what I've got:\n{summary}\n\nWant to add anything? Type a message, send a voice note 🎙️, or tap Done."

Q3_NEIGHBORHOODS_MSG = "*Which area of NYC works best for you?*"

Q3_NEIGHBORHOODS_OPTIONS = [
    {"id": "manhattan_upper", "title": "🏙️ Upper Manhattan", "description": "UWS, UES, Harlem"},
    {"id": "manhattan_mid", "title": "🌆 Midtown", "description": "Midtown, Chelsea, Flatiron"},
    {"id": "manhattan_lower", "title": "🗽 Lower Manhattan", "description": "Village, FiDi, LES"},
    {"id": "brooklyn", "title": "🌉 Brooklyn", "description": "All Brooklyn neighborhoods"},
    {"id": "queens", "title": "👑 Queens", "description": "All Queens neighborhoods"},
    {"id": "bronx", "title": "🦁 Bronx", "description": "All Bronx neighborhoods"},
    {"id": "staten_island", "title": "⛴️ Staten Island", "description": "All SI neighborhoods"},
    {"id": "anywhere", "title": "📍 Anywhere in NYC", "description": "No location preference"},
]

Q4_BUDGET_MSG = "*What\'s your typical budget for a kids activity?*"

Q4_BUDGET_BUTTONS = [
    {"id": "free", "title": "🆓 Free only"},
    {"id": "under_25", "title": "💵 Under $25"},
    {"id": "under_50", "title": "💰 Under $50"},
    {"id": "under_75", "title": "💎 Under $75"},
    {"id": "under_100", "title": "🏆 Under $100"},
]

Q5_PREFERENCES_MSG = (
    "Anything else I should know?\n"
    "(indoor/outdoor preference, allergies, accessibility needs, etc.)\n\n"
    "Or just tap Skip if nothing comes to mind."
)

Q5_SKIP_BUTTON = [
    {"id": "skip", "title": "⏭️ Skip"},
]

ONBOARDING_COMPLETE_MSG = (
    "You\'re all set! Now I know your family. 🎉\n\n"
    "Tell me what kind of event you\'re looking for — "
    "type a message or send a voice note. 🎙️\n\n"
    "For example: \"Something fun for this Saturday\" or "
    "\"Outdoor activities this weekend near Brooklyn\""
)

ASK_DAY_MSG = "*Which day are you looking for?*"

ASK_DAY_BUTTONS = [
    {"id": "today", "title": "📅 Today"},
    {"id": "tomorrow", "title": "📅 Tomorrow"},
    {"id": "this_weekend", "title": "🗓️ This Weekend"},
    {"id": "other_date", "title": "✏️ Other date"},
]

SEARCHING_MSG = "🔍 Looking for the best events for you..."

NO_RESULTS_MSG = (
    "😔 I couldn\'t find events matching all your criteria.\n\n"
    "Would you like me to broaden the search?"
)

NO_RESULTS_BUTTONS = [
    {"id": "broaden", "title": "🔄 Yes, broaden"},
    {"id": "new_search", "title": "🆕 New search"},
]

FOLLOW_UP_MSG = (
    "Hope you find something great! 🌟\n\n"
    "Send me a message anytime to search for more events."
)

PDF_OFFER_BUTTONS = [
    {"id": "send_pdf", "title": "📄 Send as PDF"},
    {"id": "more_options", "title": "🔎 More options"},
    {"id": "done", "title": "✅ That\'s all, thanks!"},
]

RESTART_KEYWORDS = {"start", "restart", "reset", "hi", "hello", "hey"}
