import os
import requests
from dotenv import load_dotenv

load_dotenv()
CONVEX_URL = (os.getenv('CONVEX_URL') or '').rstrip('/')
if not CONVEX_URL:
    print('CONVEX_URL not set')
    exit(1)

def cm(path, args):
    try:
        r = requests.post(f'{CONVEX_URL}/api/mutation',
            json={'path': path, 'args': args, 'format': 'json'},
            timeout=20)
        return r.json()
    except Exception as e:
        print(f'[{path}] {e}')
        return None

ALL_LANGS = [
    # === English (itself, learnable from other langs) ===
    ('en', 'English', 'English', '🇬🇧'),

    # === Major European ===
    ('es', 'Spanish', 'Español', '🇪🇸'),
    ('fr', 'French', 'Français', '🇫🇷'),
    ('de', 'German', 'Deutsch', '🇩🇪'),
    ('it', 'Italian', 'Italiano', '🇮🇹'),
    ('pt', 'Portuguese', 'Português', '🇵🇹'),
    ('nl', 'Dutch', 'Nederlands', '🇳🇱'),
    ('ru', 'Russian', 'Русский', '🇷🇺'),
    ('pl', 'Polish', 'Polski', '🇵🇱'),
    ('el', 'Greek', 'Ελληνικά', '🇬🇷'),
    ('sv', 'Swedish', 'Svenska', '🇸🇪'),
    ('tr', 'Turkish', 'Türkçe', '🇹🇷'),

    # === Duolingo-specific European ===
    ('no', 'Norwegian', 'Norsk', '🇳🇴'),
    ('da', 'Danish', 'Dansk', '🇩🇰'),
    ('ga', 'Irish', 'Gaeilge', '🇮🇪'),
    ('cy', 'Welsh', 'Cymraeg', '🏴󠁧󠁢󠁷󠁬󠁳󠁿'),
    ('gd', 'Scottish Gaelic', 'Gàidhlig', '🏴󠁧󠁢󠁳󠁣󠁴󠁿'),
    ('eo', 'Esperanto', 'Esperanto', '🌍'),
    ('cs', 'Czech', 'Čeština', '🇨🇿'),
    ('uk', 'Ukrainian', 'Українська', '🇺🇦'),
    ('hu', 'Hungarian', 'Magyar', '🇭🇺'),
    ('fi', 'Finnish', 'Suomi', '🇫🇮'),
    ('ro', 'Romanian', 'Română', '🇷🇴'),
    ('yi', 'Yiddish', 'ייִדיש', '✡️'),
    ('la', 'Latin', 'Latina', '🏛️'),
    ('gl', 'Galician', 'Galego', '🇪🇸'),
    ('ca', 'Catalan', 'Català', '🇪🇸'),
    ('eu', 'Basque', 'Euskara', '🇪🇸'),
    ('is', 'Icelandic', 'Íslenska', '🇮🇸'),

    # === Middle East / Africa ===
    ('ar', 'Arabic', 'العربية', '🇸🇦'),
    ('he', 'Hebrew', 'עברית', '🇮🇱'),
    ('fa', 'Persian', 'فارسی', '🇮🇷'),
    ('sw', 'Swahili', 'Kiswahili', '🇰🇪'),
    ('ht', 'Haitian Creole', 'Kreyòl Ayisyen', '🇭🇹'),
    ('zu', 'Zulu', 'isiZulu', '🇿🇦'),
    ('af', 'Afrikaans', 'Afrikaans', '🇿🇦'),
    ('am', 'Amharic', 'አማርኛ', '🇪🇹'),

    # === South Asian ===
    ('hi', 'Hindi', 'हिन्दी', '🇮🇳'),
    ('ta', 'Tamil', 'தமிழ்', '🇮🇳'),
    ('te', 'Telugu', 'తెలుగు', '🇮🇳'),
    ('bn', 'Bengali', 'বাংলা', '🇧🇩'),
    ('mr', 'Marathi', 'मराठी', '🇮🇳'),
    ('pa', 'Punjabi', 'ਪੰਜਾਬੀ', '🇮🇳'),
    ('gu', 'Gujarati', 'ગુજરાતી', '🇮🇳'),
    ('kn', 'Kannada', 'ಕನ್ನಡ', '🇮🇳'),
    ('ml', 'Malayalam', 'മലയാളം', '🇮🇳'),
    ('ur', 'Urdu', 'اردو', '🇵🇰'),
    ('sa', 'Sanskrit', 'संस्कृतम्', '🕉️'),
    ('ne', 'Nepali', 'नेपाली', '🇳🇵'),
    ('si', 'Sinhala', 'සිංහල', '🇱🇰'),
    ('as', 'Assamese', 'অসমীয়া', '🇮🇳'),
    ('or', 'Odia', 'ଓଡ଼ିଆ', '🇮🇳'),

    # === East / Southeast Asian ===
    ('ja', 'Japanese', '日本語', '🇯🇵'),
    ('ko', 'Korean', '한국어', '🇰🇷'),
    ('zh-CN', 'Chinese', '中文', '🇨🇳'),
    ('th', 'Thai', 'ไทย', '🇹🇭'),
    ('vi', 'Vietnamese', 'Tiếng Việt', '🇻🇳'),
    ('id', 'Indonesian', 'Bahasa', '🇮🇩'),
    ('ms', 'Malay', 'Bahasa Melayu', '🇲🇾'),
    ('tl', 'Filipino', 'Tagalog', '🇵🇭'),
    ('my', 'Burmese', 'မြန်မာ', '🇲🇲'),
    ('km', 'Khmer', 'ភាសាខ្មែរ', '🇰🇭'),

    # === Duolingo fun / constructed ===
    ('nv', 'Navajo', 'Diné bizaad', '🪶'),
    ('haw', 'Hawaiian', 'ʻŌlelo Hawaiʻi', '🌺'),
    ('tlh', 'Klingon', 'tlhIngan Hol', '🖖'),
    ('val', 'High Valyrian', 'Valyrio Muño', '🐉'),
]

UNITS = [
    (1, 'Greetings', 'Say hello, goodbye, please, thank you', '👋', 'A1'),
    (2, 'Numbers & Time', 'Count 1-100, tell time', '🔢', 'A1'),
    (3, 'Family & People', 'Family members, introductions', '👨‍👩‍👧', 'A1'),
    (4, 'Food & Drinks', 'Restaurant, ordering, meals', '🍽️', 'A1'),
    (5, 'Daily Routine', 'Morning to night activities', '☀️', 'A2'),
    (6, 'Travel & Directions', 'Airport, hotel, asking way', '✈️', 'A2'),
]

def seed_lang(code, name, native, flag, from_lang, description):
    cm('language:seedLanguage', {
        'code': code, 'name': name, 'native_name': native,
        'flag': flag, 'from_lang': from_lang, 'description': description,
    })

def seed_units(code, from_lang):
    for (num, title, udesc, icon, cefr) in UNITS:
        cm('language:seedUnit', {
            'language_code': code, 'from_lang': from_lang,
            'unit_number': num, 'title': title, 'description': udesc,
            'icon': icon, 'cefr_level': cefr,
        })

# Seed English → all languages (skip English → English)
print('\n=== Seeding English → All Languages ===')
for (code, name, native, flag) in ALL_LANGS:
    if code == 'en':
        continue  # skip English → English
    desc = f'Learn {name} from English'
    seed_lang(code, name, native, flag, 'en', desc)
    seed_units(code, 'en')
    print(f'  ✓ {code}')

# Seed Hindi → English + key languages
print('\n=== Seeding Hindi → Key Languages ===')
hindi_targets = ['en', 'es', 'fr', 'de', 'ja', 'ko', 'zh-CN', 'ta', 'te',
                 'bn', 'mr', 'sa', 'gu', 'kn', 'ml', 'pa', 'ur', 'ne', 'si']
for code in hindi_targets:
    item = next((x for x in ALL_LANGS if x[0] == code), None)
    if not item:
        continue
    (c, name, native, flag) = item
    desc = f'Learn {name} from Hindi'
    seed_lang(c, name, native, flag, 'hi', desc)
    seed_units(c, 'hi')
    print(f'  ✓ hi → {c}')

# Seed Indian languages → English
print('\n=== Seeding Indian Languages → English ===')
for learner in ['ta', 'te', 'bn', 'mr', 'pa', 'gu', 'kn', 'ml', 'ur',
                'hi', 'as', 'or', 'ne', 'si']:
    seed_lang('en', 'English', 'English', '🇬🇧', learner,
              f'Learn English from {learner}')
    seed_units('en', learner)
    print(f'  ✓ {learner} → en')

print('\n✅ Seeding complete!')