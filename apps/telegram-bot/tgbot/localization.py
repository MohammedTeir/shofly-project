DEFAULT = "ar"

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "welcome": "🎬 Welcome to Shofly, {name}!\nBrowse the library, search by title, or save favorites.",
        "menu_browse": "🎞 Browse", "menu_search": "🔎 Search", "menu_favorites": "❤️ Favorites",
        "menu_language": "🌐 Language", "menu_open": "📱 Open Shofly",
        "choose_language": "Choose your language:", "language_saved": "Language set to English ✅",
        "search_prompt": "Send me a title to search for.",
        "no_results": "No results for “{q}”.", "results_title": "Results for “{q}”:",
        "browse_title": "What would you like to browse?", "movies": "🎬 Movies", "series": "📺 Series",
        "next": "Next ▶", "prev": "◀ Previous", "back": "⬅ Back",
        "fav_add": "❤️ Add to favorites", "fav_remove": "💔 Remove from favorites",
        "fav_saved": "Added to favorites", "fav_removed": "Removed from favorites",
        "favorites_title": "Your favorites:", "favorites_empty": "You have no favorites yet.",
        "browse_empty": "Nothing here yet.", "original_title": "Original title",
        "season_label": "Season {n}", "specials": "Specials", "episodes_empty": "No episodes listed.",
        "not_found": "This title is no longer available.",
        "error": "Something went wrong. Please try again.",
        "throttled": "Too many requests. Please slow down.",
        "delivery_pending": "No downloadable file is available for this title yet.",
        "send_file": "📥 Send me the file", "sending": "Sending…", "delivery_denied": "This file isn't available to you right now.",
        "delivery_failed": "Couldn't send the file. Please try again later.",
        "help": "Commands:\n/browse – browse movies and series\n/search – search by title\n/favorites – your favorites\n/language – change language\n/help – this message",
        "cmd_start": "Start", "cmd_browse": "Browse", "cmd_search": "Search",
        "cmd_favorites": "Favorites", "cmd_language": "Change language", "cmd_help": "Help",
    },
    "ar": {
        "welcome": "🎬 أهلاً بك في شوفلي {name}!\nتصفّح المكتبة أو ابحث عن عنوان أو احفظ مفضّلاتك.",
        "menu_browse": "🎞 تصفّح", "menu_search": "🔎 بحث", "menu_favorites": "❤️ المفضلة",
        "menu_language": "🌐 اللغة", "menu_open": "📱 افتح شوفلي",
        "choose_language": "اختر لغتك:", "language_saved": "تم تعيين اللغة: العربية ✅",
        "search_prompt": "أرسل لي اسم العنوان للبحث عنه.",
        "no_results": "لا توجد نتائج لـ «{q}».", "results_title": "نتائج «{q}»:",
        "browse_title": "ماذا تريد أن تتصفح؟", "movies": "🎬 الأفلام", "series": "📺 المسلسلات",
        "next": "التالي ◀", "prev": "▶ السابق", "back": "➡ رجوع",
        "fav_add": "❤️ أضف إلى المفضلة", "fav_remove": "💔 إزالة من المفضلة",
        "fav_saved": "أُضيف إلى المفضلة", "fav_removed": "أُزيل من المفضلة",
        "favorites_title": "مفضلتك:", "favorites_empty": "لا توجد عناصر في المفضلة بعد.",
        "browse_empty": "لا يوجد محتوى بعد.", "original_title": "العنوان الأصلي",
        "season_label": "الموسم {n}", "specials": "حلقات خاصة", "episodes_empty": "لا توجد حلقات.",
        "not_found": "هذا العنوان لم يعد متاحاً.",
        "error": "حدث خطأ ما. حاول مرة أخرى.",
        "throttled": "طلبات كثيرة. الرجاء التمهّل.",
        "delivery_pending": "لا يوجد ملف متاح لهذا العنوان بعد.",
        "send_file": "📥 أرسل لي الملف", "sending": "جارٍ الإرسال…", "delivery_denied": "هذا الملف غير متاح لك حالياً.",
        "delivery_failed": "تعذّر إرسال الملف. حاول لاحقاً.",
        "help": "الأوامر:\n/browse – تصفّح الأفلام والمسلسلات\n/search – بحث بالعنوان\n/favorites – مفضلتك\n/language – تغيير اللغة\n/help – هذه الرسالة",
        "cmd_start": "ابدأ", "cmd_browse": "تصفّح", "cmd_search": "بحث",
        "cmd_favorites": "المفضلة", "cmd_language": "تغيير اللغة", "cmd_help": "مساعدة",
    },
}


def t(lang: str | None, key: str, **kw) -> str:
    text = STRINGS.get(lang or DEFAULT, STRINGS[DEFAULT])[key]
    return text.format(**kw) if kw else text
