"""
NOVEX AI — Backend Engine v8.1 (UPGRADED)
ChatGPT-quality replies + All features
Improvements: thread-safety, retry, LRU, better search, robust JSON,
              expanded lingua, fixed bugs, streaming timeouts.
"""
from __future__ import annotations
import base64, datetime, hashlib, json as _json, os, random as _random
import re, time as _time, uuid, threading
from collections import defaultdict, OrderedDict
from threading import Lock, RLock
from urllib.parse import quote
import xml.etree.ElementTree as ET

import requests
from ddgs import DDGS
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# CONFIG
# ============================================================
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
CONVEX_URL = (os.getenv("CONVEX_URL") or "").rstrip("/")

SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
SEARCH_PROVIDER = os.getenv("SEARCH_DEFAULT_PROVIDER", "serper").lower()
SEARCH_MAX_RESULTS = int(os.getenv("SEARCH_MAX_RESULTS", "6"))
SEARCH_REGION = os.getenv("SEARCH_REGION", "in-en")
SEARCH_SAFE = os.getenv("SEARCH_SAFE", "true").lower() == "true"

GROQ_MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b",
               "llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
DEFAULT_MODEL = "groq:openai/gpt-oss-120b"
_ACTIVE_MODEL = DEFAULT_MODEL

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

# Retry config
GROQ_MAX_RETRIES = int(os.getenv("GROQ_MAX_RETRIES", "2"))
GROQ_RETRY_BACKOFF = float(os.getenv("GROQ_RETRY_BACKOFF", "0.8"))
GROQ_TIMEOUT = int(os.getenv("GROQ_TIMEOUT", "60"))

# Session config
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "20"))
MAX_SESSIONS = int(os.getenv("MAX_SESSIONS", "500"))  # LRU cap

# ============================================================
# 🌟 CHATGPT-LEVEL SYSTEM PROMPTS
# ============================================================
DEFAULT_SYSTEM = """You are NOVEX — a helpful, thoughtful, and highly capable AI assistant.

## Response Style (ChatGPT-level quality):

1. **Structured answers** — use headings (##), bullets, numbered lists
2. **Bold key concepts** for scannability
3. **Code blocks** with language tags for any code
4. **Tables** when comparing 3+ items
5. **Clickable links** as [title](url) — ALWAYS include real URLs
6. **Real examples** — not just theory
7. **Step-by-step** for how-to questions
8. **Analogies** for complex concepts
9. **Match user's language** — Hindi, English, or Hinglish
10. **Concise but complete** — no fluff, no padding

## Response Structure:

**HOW-TO questions:**
- Quick answer (1 line)
- 3-5 numbered steps
- Code/example if applicable
- Common mistakes (optional)

**EXPLAIN questions:**
- Simple answer (1-2 lines)
- Analogy
- Detailed breakdown with headings
- Example
- Key takeaways

**COMPARISON:**
- Table with differences
- When to use which
- Pros/cons

**CODE:**
- Complete runnable code
- Hindi comments on tricky lines
- Explanation after code

**LINKS:**
- Always give full URLs as markdown: [Title](https://full-url.com)
- Wikipedia, official docs, GitHub, news — actual working links
- Never say "you can find it" without giving link

## NEVER:
- Give shallow answers
- Use "as an AI language model" disclaimers
- Refuse reasonable requests
- Pad with useless filler
- Use emojis excessively (1-2 max)

Aim: ChatGPT/Claude-level quality. Make every response worth reading."""


DEEP_EXPLAIN_SYSTEM = """You are NOVEX in DEEP EXPLAIN mode — world-class teacher.

## Structure:

### 🎯 One-line Answer
Single simple sentence.

### 🌟 Real-life Analogy
Connect to something familiar — cricket, chai, traffic, cooking, school.

### 📚 Detailed Breakdown
Numbered steps with clear headings.

### 💡 Concrete Example
Walk through real example step-by-step with numbers/code.

### ⚠️ Common Mistakes
2-3 mistakes students typically make.

### ✅ Summary
2-line essence.

## Formatting:
- **Bold** for key terms
- `code` for variables/functions
- Code blocks with language tags
- Tables when comparing
- [Clickable links](https://example.com) for references
- Match user's language

NEVER shallow. Explain WHY, not just WHAT."""


PERSONAS = {
    "default": DEFAULT_SYSTEM,
    "coder": """You are NOVEX in CODER mode — senior engineer, 15+ years experience.

RULES:
1. Complete runnable code — not snippets
2. Type hints for Python
3. Error handling — try/except, edge cases
4. Hindi comments on non-obvious lines
5. Explain after code
6. Production quality
7. Mention alternatives when 2+ approaches exist

Format: Code block first, then explanation. Never partial code.""",
    "webdev": """You are NOVEX in WEB DEV mode — full-stack engineer.

RULES:
1. Mobile-first responsive
2. Semantic HTML5
3. Modern CSS (flex/grid/custom props)
4. Vanilla JS unless framework asked
5. Complete files, copy-paste ready
6. Accessibility (aria, keyboard)

Format: HTML + CSS + JS in separate code blocks.""",
    "teacher": """You are NOVEX in TEACHER mode — patient, clear, structured.

RULES:
1. Assume no prior knowledge
2. Everyday examples (cricket, food, daily life)
3. Step-by-step
4. End with a mini-quiz question
5. Encouraging tone
6. Simple language, no jargon

Perfect for students of all ages.""",
    "friend": """You are NOVEX in FRIEND mode — casual, fun.

RULES:
1. Hinglish natural mix
2. Short punchy (2-3 lines usually)
3. 1-2 emojis max
4. Casual tone
5. Skip formality

Example: "Arre yaar, simple hai! Bas yeh karo..." """,
    "guru": """You are NOVEX in GURU mode — deep, philosophical, wise.

RULES:
1. Warm compassionate tone 🙏
2. Deeper meaning beyond surface
3. Indian philosophy analogies
4. Practical wisdom
5. Encourage reflection

End with a thought-provoking line.""",
}

# ============================================================
# PER-SESSION STATE (LRU capped)
# ============================================================
_HISTORY_LOCK = RLock()
_chat_history: "OrderedDict[str, list]" = OrderedDict()
_last_code: "OrderedDict[str, str]" = OrderedDict()
_current_mode: "OrderedDict[str, str]" = OrderedDict()
_quiz_state: "OrderedDict[str, dict]" = OrderedDict()

def _default_quiz():
    return {
        "active": False, "topic": "", "difficulty": "medium",
        "questions": [], "current_index": 0, "score": 0,
        "correct": 0, "wrong": 0, "user_answers": [],
        "streak": 0, "max_streak": 0, "time_left": 30,
        "hint_used": False, "hint_available": 1,
        "xp_multiplier": 1.0, "question_start": 0,
    }

def _lru_touch(d, key, default=None):
    """Touch key in OrderedDict for LRU. Creates if missing."""
    if key in d:
        d.move_to_end(key)
        return d[key]
    if default is not None:
        d[key] = default
        d.move_to_end(key)
        # Evict oldest
        while len(d) > MAX_SESSIONS:
            d.popitem(last=False)
        return d[key]
    return None

def _get_quiz(sid):
    with _HISTORY_LOCK:
        if sid in _quiz_state:
            _quiz_state.move_to_end(sid)
            return _quiz_state[sid]
        _quiz_state[sid] = _default_quiz()
        while len(_quiz_state) > MAX_SESSIONS:
            _quiz_state.popitem(last=False)
        return _quiz_state[sid]

def clear_session(sid):
    """Clear all session state for a given id."""
    with _HISTORY_LOCK:
        _chat_history.pop(sid, None)
        _last_code.pop(sid, None)
        _current_mode.pop(sid, None)
        _quiz_state.pop(sid, None)

def get_session_info():
    with _HISTORY_LOCK:
        return {
            "sessions": len(_chat_history),
            "quizzes_active": sum(1 for q in _quiz_state.values() if q.get("active")),
            "total_quizzes": len(_quiz_state),
            "max_sessions": MAX_SESSIONS,
        }

_on_usage = None

# ============================================================
# SEARCH — Serper + DDGS (thread-safe cache)
# ============================================================
_SEARCH_CACHE: "OrderedDict[str, tuple]" = OrderedDict()
_SEARCH_CACHE_TTL = int(os.getenv("SEARCH_CACHE_TTL", "300"))
_SEARCH_CACHE_MAX = int(os.getenv("SEARCH_CACHE_MAX", "500"))
_SEARCH_LOCK = Lock()
_last_search_provider = ""


def _cache_get(key):
    with _SEARCH_LOCK:
        entry = _SEARCH_CACHE.get(key)
        if not entry:
            return None
        ts, data = entry
        if _time.time() - ts > _SEARCH_CACHE_TTL:
            _SEARCH_CACHE.pop(key, None)
            return None
        _SEARCH_CACHE.move_to_end(key)
        return data


def _cache_set(key, data):
    with _SEARCH_LOCK:
        _SEARCH_CACHE[key] = (_time.time(), data)
        _SEARCH_CACHE.move_to_end(key)
        while len(_SEARCH_CACHE) > _SEARCH_CACHE_MAX:
            _SEARCH_CACHE.popitem(last=False)


def _dedupe_results(results):
    """Dedupe by URL, keep first."""
    seen = set()
    out = []
    for r in results:
        url = (r.get("url") or "").strip().rstrip("/")
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(r)
    return out


def _clean_snippet(s):
    if not s:
        return ""
    s = re.sub(r"\s+", " ", str(s)).strip()
    return s[:400]


def _search_serper(query, max_results=6):
    if not SERPER_API_KEY:
        return []
    try:
        res = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            json={
                "q": query,
                "num": max_results,
                "gl": SEARCH_REGION.split("-")[-1] if "-" in SEARCH_REGION else "in",
                "hl": "en",
            },
            timeout=12,
        )
        if res.status_code != 200:
            return []
        data = res.json()
        out = []
        kg = data.get("knowledgeGraph", {})
        if kg and kg.get("title"):
            out.append({
                "title": kg.get("title", "")[:200],
                "url": kg.get("descriptionLink") or kg.get("website", ""),
                "snippet": _clean_snippet(kg.get("description") or ""),
                "source": "google-kg",
            })
        ab = data.get("answerBox", {})
        if ab:
            text = ab.get("answer") or ab.get("snippet") or ""
            if text:
                out.insert(0, {
                    "title": ab.get("title", "Quick Answer"),
                    "url": ab.get("link", ""),
                    "snippet": _clean_snippet(text),
                    "source": "google-answer",
                })
        for r in data.get("organic", [])[:max_results]:
            url = (r.get("link") or "").strip()
            if url:
                out.append({
                    "title": (r.get("title") or "").strip()[:200],
                    "url": url,
                    "snippet": _clean_snippet(r.get("snippet") or ""),
                    "source": "google",
                })
        return _dedupe_results(out)[:max_results]
    except Exception as e:
        print(f"[search:serper] {e}", flush=True)
        return []


def _search_ddgs(query, max_results=6):
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(
                query, max_results=max_results,
                region=SEARCH_REGION,
                safesearch="moderate" if SEARCH_SAFE else "off",
            ))
        out = []
        for r in results:
            url = (r.get("href") or r.get("url") or "").strip()
            if url:
                out.append({
                    "title": (r.get("title") or "").strip()[:200],
                    "url": url,
                    "snippet": _clean_snippet(r.get("body") or ""),
                    "source": "duckduckgo",
                })
        return _dedupe_results(out)
    except Exception as e:
        print(f"[search:ddgs] {e}", flush=True)
        return []


def web_search_structured(query, max_results=None):
    global _last_search_provider
    if not query or not query.strip():
        return []
    max_results = max_results or SEARCH_MAX_RESULTS
    cache_key = hashlib.md5(
        f"{query}:{max_results}:{SEARCH_PROVIDER}".encode()
    ).hexdigest()
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    order = ["ddgs", "serper"] if SEARCH_PROVIDER == "ddgs" else ["serper", "ddgs"]
    results = []
    used = None
    for provider in order:
        if provider == "serper":
            results = _search_serper(query, max_results)
        elif provider == "ddgs":
            results = _search_ddgs(query, max_results)
        if results:
            used = provider
            break
    _last_search_provider = used or "none"
    _cache_set(cache_key, results)
    return results


def format_search_results_with_citations(query, results):
    if not results:
        return f"### 🔍 Search: {query}\n\n_Koi result nahi mila._\n"
    out = f"### 🔍 Search: {query}\n\n"
    for i, r in enumerate(results, 1):
        out += f"**[{i}] {r.get('title', 'Untitled')}**\n"
        if r.get("snippet"):
            out += f"{r['snippet']}\n\n"
        if r.get("url"):
            out += f"🔗 [{r['url']}]({r['url']})"
            if r.get("source"):
                out += f" · `{r['source']}`"
            out += "\n\n---\n\n"
    out += f"_📊 {len(results)} sources via {_last_search_provider}_\n"
    return out


def web_search(query):
    return format_search_results_with_citations(query, web_search_structured(query))


def get_news(topic=None, max_items=5):
    try:
        with DDGS() as ddgs:
            news = list(ddgs.news(
                topic or "India", max_results=max_items, region=SEARCH_REGION,
            ))
        if not news:
            return f"**News** ({topic or 'India'}): koi result nahi mila."
        out = f"### 📰 Latest News — {topic or 'India'}\n\n"
        for i, n in enumerate(news, 1):
            title = (n.get("title") or "").strip()
            url = n.get("url", "") or n.get("href", "")
            body = (n.get("body") or "").strip()[:200]
            date = (n.get("date") or "")[:10]
            source = n.get("source", "")
            out += f"**{i}. {title}**"
            if date:
                out += f" `{date}`"
            if source:
                out += f" · _{source}_"
            out += "\n"
            if body:
                out += f"{body}\n\n"
            if url:
                out += f"🔗 [Read full article]({url})\n\n"
        return out.strip()
    except Exception as e:
        return f"News error: {e}"


# ============================================================
# GROQ CALL (with retry)
# ============================================================
def _groq_call(prompt, temp=0.7, timeout=None, model=None, system=None,
               max_tokens=None):
    if not GROQ_API_KEY:
        return None
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})

    payload = {
        "model": model or "openai/gpt-oss-20b",
        "messages": msgs,
        "temperature": temp,
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    last_err = None
    for attempt in range(GROQ_MAX_RETRIES + 1):
        try:
            res = requests.post(url, headers=headers, json=payload,
                                timeout=timeout or GROQ_TIMEOUT)
            if res.status_code == 200:
                return res.json()["choices"][0]["message"]["content"]
            if res.status_code in (429, 500, 502, 503, 504):
                last_err = f"HTTP {res.status_code}"
                _time.sleep(GROQ_RETRY_BACKOFF * (attempt + 1))
                continue
            last_err = f"HTTP {res.status_code}: {res.text[:120]}"
            break
        except requests.Timeout:
            last_err = "timeout"
            _time.sleep(GROQ_RETRY_BACKOFF * (attempt + 1))
        except Exception as e:
            last_err = str(e)
            _time.sleep(GROQ_RETRY_BACKOFF * (attempt + 1))
    if last_err:
        print(f"[groq_call] {last_err}", flush=True)
    return None


def _models_for_call():
    fb = list(GROQ_MODELS)
    if _ACTIVE_MODEL.startswith("groq:"):
        pref = _ACTIVE_MODEL.replace("groq:", "")
        if pref in fb:
            fb.remove(pref)
        fb.insert(0, pref)
    return fb


# ============================================================
# VISION
# ============================================================
VISION_MODELS = [
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "llama-3.2-90b-vision-preview",
    "llama-3.2-11b-vision-preview",
]


def _encode_image_base64(path):
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        print(f"[encode_image] {e}", flush=True)
        return None


def solve_image(image_path, question="", language="hinglish"):
    if not GROQ_API_KEY:
        return "⚠️ GROQ_API_KEY missing."
    b64 = _encode_image_base64(image_path)
    if not b64:
        return "⚠️ Could not read image."
    ext = os.path.splitext(image_path)[1].lower().lstrip(".")
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "webp": "image/webp", "gif": "image/gif"}.get(ext, "image/jpeg")

    system = (
        "You are NOVEX in DOUBT SOLVER mode.\n\n"
        "RULES:\n1. Describe image (1 line).\n2. Identify subject.\n"
        "3. Solve STEP-BY-STEP.\n4. Show formulas.\n5. Final answer in bold.\n"
        "6. Add similar practice problem.\n"
        f"7. Language: {language}.\n8. Markdown."
    )
    user_text = question.strip() or "Solve this step-by-step."
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}",
               "Content-Type": "application/json"}

    for model in VISION_MODELS:
        for attempt in range(GROQ_MAX_RETRIES + 1):
            try:
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": [
                            {"type": "text", "text": user_text},
                            {"type": "image_url",
                             "image_url": {"url": f"data:{mime};base64,{b64}"}},
                        ]},
                    ],
                    "temperature": 0.4,
                    "max_tokens": 2048,
                }
                r = requests.post(url, headers=headers, json=payload, timeout=90)
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"]
                if r.status_code in (429, 500, 503):
                    _time.sleep(GROQ_RETRY_BACKOFF * (attempt + 1))
                    continue
                break
            except Exception as e:
                print(f"[vision:{model}] {e}", flush=True)
                _time.sleep(GROQ_RETRY_BACKOFF * (attempt + 1))
    return "⚠️ Vision model unavailable. Try again."


# ============================================================
# SRS
# ============================================================
def srs_next(ease_factor=2.5, interval_days=0, repetitions=0, rating=2):
    quality = {0: 1, 1: 3, 2: 4, 3: 5}.get(rating, 4)
    if quality < 3:
        repetitions = 0
        interval_days = 1
    else:
        if repetitions == 0:
            interval_days = 1
        elif repetitions == 1:
            interval_days = 6
        else:
            interval_days = round(interval_days * ease_factor)
        repetitions += 1
    ef = ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    if ef < 1.3:
        ef = 1.3
    now_ms = int(datetime.datetime.now().timestamp() * 1000)
    return {
        "ease_factor": round(ef, 2),
        "interval_days": interval_days,
        "repetitions": repetitions,
        "next_review": now_ms + interval_days * 86400000,
        "last_rating": rating,
        "last_reviewed": now_ms,
    }


# ============================================================
# GAMIFICATION
# ============================================================
LEVELS = [(0, "Beginner", "🌱"), (100, "Learner", "📖"), (500, "Scholar", "🎓"),
          (2000, "Master", "🧠"), (10000, "Legend", "🏆")]

EXP_REWARDS = {
    "chat_message": 1, "quiz_correct": 10, "quiz_complete": 25,
    "quiz_perfect": 50, "quiz_streak_5": 30, "quiz_streak_10": 75,
    "flashcard_review": 5, "flashcard_deck_create": 15,
    "doc_generate": 20, "study_plan_create": 15,
    "pomodoro_complete": 30, "doubt_scanner": 15, "streak_day": 20,
    "language_lesson": 30, "language_chat": 3, "language_review": 5,
}

BADGES = {
    "first_chat": ("💬", "First Words", "Sent your first message"),
    "first_quiz": ("🎯", "Quiz Rookie", "Completed your first quiz"),
    "quiz_master": ("🎓", "Quiz Master", "Completed 50 quizzes"),
    "perfect_quiz": ("💯", "Perfect Score", "Got 100% on a quiz"),
    "streak_7": ("🔥", "Week Warrior", "7-day study streak"),
    "streak_30": ("🔥🔥", "Month Master", "30-day study streak"),
    "flashcard_100": ("📚", "Card Shark", "Reviewed 100 flashcards"),
    "doc_writer": ("📝", "Author", "Generated 10 documents"),
    "focus_10": ("⏱️", "Focus Ninja", "10 Pomodoro sessions"),
    "doubt_solver": ("📸", "Doubt Destroyer", "Solved 10 doubts from photos"),
    "memory_keeper": ("🧠", "Elephant", "Saved 20 memories"),
    "polyglot_1": ("🦜", "First Steps", "First language lesson"),
    "polyglot_10": ("🌍", "Explorer", "10 language lessons"),
    "polyglot_50": ("🎓", "Polyglot", "50 language lessons"),
    "vocab_100": ("📖", "Word Collector", "Learned 100 words"),
    "vocab_500": ("📚", "Lexicon", "Learned 500 words"),
}


def calculate_level(exp):
    current = LEVELS[0]
    next_lvl = None
    for i, (threshold, name, icon) in enumerate(LEVELS):
        if exp >= threshold:
            current = (threshold, name, icon)
            next_lvl = LEVELS[i + 1] if i + 1 < len(LEVELS) else None
        else:
            break
    result = {
        "level": current[1], "icon": current[2],
        "exp": exp, "level_start": current[0],
    }
    if next_lvl:
        result["next_level"] = next_lvl[1]
        result["next_at"] = next_lvl[0]
        result["progress_pct"] = round(
            ((exp - current[0]) / (next_lvl[0] - current[0])) * 100
        )
    else:
        result["next_level"] = None
        result["next_at"] = None
        result["progress_pct"] = 100
    return result


def build_system_prompt(mode="default", custom_instructions="",
                        user_personas=None, memory=None):
    base = PERSONAS.get(mode, PERSONAS["default"])
    if user_personas and mode in user_personas:
        p = user_personas[mode]
        base = f"{p.get('prompt', base)}\n\n(You are acting as '{p.get('name', mode)}'.)"
    parts = [base]
    if memory:
        facts = "\n".join(
            f"- {m.get('fact', '')}" for m in memory[-30:] if m.get("fact")
        )
        if facts:
            parts.append(f"\n\nWHAT YOU REMEMBER:\n{facts}\n\nUse naturally.")
    if custom_instructions and custom_instructions.strip():
        parts.append("\n\nUSER INSTRUCTIONS:\n" + custom_instructions.strip()[:3000])
    return "\n".join(parts)


def _strip_json_fence(s):
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json|markdown|md)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s


def _sanitize_json(s):
    # Remove trailing commas
    s = re.sub(r",(\s*[}\]])", r"\1", s)
    # Smart quotes
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    s = s.replace("\u2018", "'").replace("\u2019", "'")
    # Control chars
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)
    return s


def _extract_json(raw, kind="object"):
    """Robust JSON extraction with repair fallback."""
    if not raw:
        return None
    raw = _strip_json_fence(raw)
    if kind == "array":
        s, e = raw.find("["), raw.rfind("]")
    else:
        s, e = raw.find("{"), raw.rfind("}")
    if s == -1 or e == -1 or e <= s:
        return None
    candidate = _sanitize_json(raw[s:e + 1])
    try:
        return _json.loads(candidate)
    except Exception:
        pass
    # Fallback: try fixing common issues
    candidate = re.sub(r"(?<!\\)\n", " ", candidate)  # newlines inside strings
    candidate = re.sub(r",\s*,", ",", candidate)
    try:
        return _json.loads(candidate)
    except Exception:
        return None


# ============================================================
# MEMORY (improved dedup + priority)
# ============================================================
def extract_facts(text):
    if not text or len(text) < 30:
        return []
    prompt = (
        "Extract STABLE personal facts about the user.\n"
        "Rules: name, job, city, preferences, goals, skills only.\n"
        "Max 5 facts. Return ONLY JSON array. NO markdown.\n\n"
        f"Text:\n{text[:4000]}"
    )
    result = _groq_call(prompt, temp=0.3)
    if not result:
        return []
    arr = _extract_json(result, kind="array")
    if not arr or not isinstance(arr, list):
        return []
    # Clean + dedupe
    seen = set()
    out = []
    for x in arr:
        s = str(x).strip()[:200]
        key = s.lower()
        if not s or key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out[:5]


# ============================================================
# FLASHCARDS
# ============================================================
def generate_flashcards(source_text, count=10):
    prompt = (
        f"Generate exactly {count} flashcards.\n\n"
        'Return ONLY JSON:\n'
        '{"title": "...", "cards": [{"front": "...", "back": "..."}]}\n\n'
        f"Rules: {count} cards, match source language, NO markdown, NO trailing commas.\n\n"
        f"Content:\n{source_text[:6000]}"
    )
    result = _groq_call(prompt, temp=0.5, timeout=90)
    if not result:
        return {"error": "Generation failed"}
    data = _extract_json(result, kind="object")
    if not data:
        return {"error": "Bad format"}
    cleaned = []
    seen = set()
    for c in data.get("cards", [])[:count]:
        if not isinstance(c, dict):
            continue
        front = str(c.get("front", "")).strip()[:300]
        back = str(c.get("back", "")).strip()[:800]
        key = front.lower()
        if front and back and key not in seen:
            seen.add(key)
            cleaned.append({"front": front, "back": back})
    if not cleaned:
        return {"error": "No valid cards"}
    return {
        "ok": True,
        "title": str(data.get("title", "Flashcards"))[:60],
        "cards": cleaned,
    }


# ============================================================
# DOCUMENT
# ============================================================
def generate_document(topic, style="essay", length="medium", language="hindi"):
    length_map = {
        "short": "300-500 words, 3 sections",
        "medium": "700-1200 words, 4-5 sections",
        "long": "1500-2500 words, 6-8 sections",
    }
    style_map = {
        "essay": "formal essay", "blog": "casual blog",
        "report": "structured report", "story": "narrative story",
        "notes": "study notes",
    }
    lang_name = {"hindi": "Hindi", "english": "English",
                 "hinglish": "Hinglish"}.get(language, "Hindi")
    length_desc = length_map.get(length, length_map["medium"])
    style_desc = style_map.get(style, style_map["essay"])

    outline_prompt = (
        f"Create outline for {style_desc} on: **{topic}**\n"
        f"Length: {length_desc}\nLanguage: {lang_name}\n\n"
        'Return ONLY JSON: {"title": "...", "outline": ["Section 1", ...]}\n'
    )
    outline_result = _groq_call(outline_prompt, temp=0.7)
    if not outline_result:
        return {"error": "Outline failed"}
    outline_data = _extract_json(outline_result, kind="object")
    if not outline_data:
        return {"error": "Bad outline"}

    title = str(outline_data.get("title", topic))[:100]
    outline = [str(x).strip() for x in outline_data.get("outline", []) if str(x).strip()]
    if not outline:
        return {"error": "No sections"}

    full = f"# {title}\n\n"
    for i, section in enumerate(outline, 1):
        sp = (
            f"Write section {i} of {style_desc}.\n"
            f"Title: {title}\nSection: {section}\n"
            f"Language: {lang_name}\n\n"
            "Rules: 100-350 words, markdown.\n\n"
            f"Context:\n{full[-1500:]}\n\nONLY this section."
        )
        sc = _groq_call(sp, temp=0.75, timeout=90)
        full += (sc.strip() if sc else f"## {section}\n\n_Failed_") + "\n\n"
    return {
        "ok": True, "title": title,
        "outline": outline, "content": full.strip(),
    }


# ============================================================
# REMINDER (improved parsing)
# ============================================================
def parse_reminder(text):
    t = text.lower().strip()
    triggers = ["yaad dila", "yaad dilaao", "remind", "reminder",
                "याद दिला", "याद रख", "याद दिलाओ"]
    if not any(tr in t for tr in triggers):
        return None
    now = datetime.datetime.now(IST)
    target = now.replace(second=0, microsecond=0)
    day_offset = 0
    if "parso" in t or "परसों" in t:
        day_offset = 2
    elif "kal" in t or "कल" in t:
        day_offset = 1

    m = re.search(r"(\d{1,2}):(\d{2})\s*(am|pm)?", t)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        ampm = m.group(3)
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        target = target.replace(hour=hour, minute=minute)
    else:
        m = re.search(r"(\d{1,2})\s*(baje|bje|बजे|o.?clock)", t)
        if not m:
            return None
        hour = int(m.group(1))
        if 1 <= hour <= 11 and not any(k in t for k in ("subah", "morning", "सुबह")):
            if any(k in t for k in ("raat", "sham", "shaam", "evening", "night")):
                hour += 12
            elif 1 <= hour <= 8:
                hour += 12
        target = target.replace(hour=hour, minute=0)
    target += datetime.timedelta(days=day_offset)
    if target <= now:
        target += datetime.timedelta(days=1)

    task = text
    for tr in triggers:
        task = re.sub(rf"{tr}[ao]?\s*", "", task, flags=re.IGNORECASE)
    task = re.sub(r"(\d{1,2}):(\d{2})\s*(am|pm)?", "", task)
    task = re.sub(r"\d{1,2}\s*(baje|bje|बजे|o.?clock)", "", task)
    task = re.sub(r"\b(kal|parso|aaj|कल|परसों|आज)\b", "", task)
    task = re.sub(r"\b(ki|that|to|ko|को|कि|है|hai)\b", "", task)
    task = re.sub(r"\s+", " ", task).strip(" ,.-:")
    return {"text": task or "Reminder", "when": target.isoformat()}


# ============================================================
# TIME (IST)
# ============================================================
def get_time():
    now = datetime.datetime.now(IST)
    days_hi = ["Somvar", "Mangalvar", "Budhvar", "Guruvar",
               "Shukravar", "Shanivar", "Ravivar"]
    return (f"Abhi **{now.strftime('%I:%M %p')}**, "
            f"{days_hi[now.weekday()]}, {now.day}/{now.month}/{now.year} (IST) ⏰")


def get_day_info(query):
    today = datetime.datetime.now(IST).date()
    fmt = lambda d: f"{d.strftime('%A')}, {d.day}/{d.month}/{d.year}"
    if "parso" in query:
        return f"Parso: **{fmt(today + datetime.timedelta(days=2))}**"
    if "kal" in query:
        return f"Kal: **{fmt(today + datetime.timedelta(days=1))}**"
    if "aaj" in query:
        return f"Aaj: **{fmt(today)}**"
    return fmt(today)


# ============================================================
# TRANSLATION
# ============================================================
_LANG_MAP = {
    "hi": "Hindi", "en": "English", "bn": "Bengali", "te": "Telugu",
    "mr": "Marathi", "ta": "Tamil", "ur": "Urdu", "gu": "Gujarati",
    "kn": "Kannada", "ml": "Malayalam", "pa": "Punjabi", "or": "Odia",
    "as": "Assamese", "ne": "Nepali", "si": "Sinhala", "es": "Spanish",
    "fr": "French", "de": "German", "it": "Italian", "pt": "Portuguese",
    "ru": "Russian", "ar": "Arabic", "fa": "Persian", "tr": "Turkish",
    "zh-CN": "Chinese Simplified", "ja": "Japanese", "ko": "Korean",
    "th": "Thai", "vi": "Vietnamese", "id": "Indonesian", "sa": "Sanskrit",
    "no": "Norwegian", "da": "Danish", "ga": "Irish", "cy": "Welsh",
    "gd": "Scottish Gaelic", "eo": "Esperanto", "cs": "Czech",
    "uk": "Ukrainian", "hu": "Hungarian", "fi": "Finnish",
    "ro": "Romanian", "yi": "Yiddish", "la": "Latin", "gl": "Galician",
    "ca": "Catalan", "eu": "Basque", "is": "Icelandic", "sw": "Swahili",
    "ht": "Haitian Creole", "zu": "Zulu", "af": "Afrikaans",
    "am": "Amharic", "ms": "Malay", "tl": "Filipino", "my": "Burmese",
    "km": "Khmer", "nv": "Navajo", "haw": "Hawaiian",
    "tlh": "Klingon", "val": "High Valyrian",
}


def translate_text(text, target_code="hi", source_code="auto"):
    target_name = _LANG_MAP.get(target_code, target_code)
    prompt = (
        f"Translate the following text to **{target_name}**.\n"
        "Rules:\n"
        "- Output ONLY the translation\n"
        "- Preserve original formatting (line breaks, markdown)\n"
        "- No explanations, no quotes around output\n\n"
        f"Text:\n{text}"
    )
    result = _groq_call(prompt, temp=0.2)
    if not result:
        return {"error": "Translation failed"}
    result = result.strip()
    if (result.startswith('"') and result.endswith('"')) or \
       (result.startswith("'") and result.endswith("'")):
        result = result[1:-1]
    return {
        "ok": True, "translated": result,
        "target": target_code, "source": source_code,
    }


# ============================================================
# QUIZ v2
# ============================================================
QUIZ_CATEGORIES = {
    "General Knowledge": "🌍", "Coding": "💻", "Mathematics": "🧮",
    "Science": "🔬", "History": "📜", "Geography": "🗺️",
    "Sports": "⚽", "Bollywood": "🎬", "Technology": "🚀",
    "Politics": "🏛️", "Business": "💼", "Health": "💚",
    "English": "📖", "Reasoning": "🧩", "Current Affairs": "📰",
}

DIFFICULTY_PRESETS = {
    "easy": {"count": 5, "time": 30, "hint": 1, "xp": 1.0},
    "medium": {"count": 10, "time": 25, "hint": 1, "xp": 1.5},
    "hard": {"count": 15, "time": 20, "hint": 0, "xp": 2.0},
    "expert": {"count": 20, "time": 15, "hint": 0, "xp": 3.0},
}


def _clean_quiz_question(q, difficulty):
    if not isinstance(q, dict):
        return None
    q_text = re.sub(r"\s+", " ", str(q.get("q", "")).replace("<br>", " ")).strip()
    if not q_text:
        return None
    options = q.get("options", [])
    if isinstance(options, str):
        options = [p.strip() for p in re.split(r"<br\s*/?>|\n", options) if p.strip()]
    clean_opts = []
    for opt in options:
        opt = re.sub(r"^[A-Da-d][\)\.\-]\s*", "", str(opt).strip())
        opt = re.sub(r"\s+", " ", opt.replace("<br>", " ")).strip()
        if opt:
            clean_opts.append(opt)
    if len(clean_opts) < 2:
        return None
    clean_opts = clean_opts[:4]
    while len(clean_opts) < 4:
        clean_opts.append("—")
    answer_raw = str(q.get("answer", "")).strip().upper()
    am = re.search(r"[A-D]", answer_raw)
    answer_letter = am.group(0) if am else "A"
    expl = re.sub(r"\s+", " ", str(q.get("explanation", "")).replace("<br>", " ")).strip()
    return {
        "q": q_text, "options": clean_opts, "answer": answer_letter,
        "explanation": expl, "difficulty": difficulty, "tags": [],
    }


def generate_quiz_json(topic="General Knowledge", difficulty="medium", count=5):
    diff_guide = {
        "easy": "basic recall, straightforward",
        "medium": "requires understanding, application",
        "hard": "tricky, multi-step, edge cases",
        "expert": "advanced, nuanced, competitive exam level",
    }
    prompt = f"""Generate exactly {count} multiple-choice quiz questions.

Topic: {topic}
Difficulty: {difficulty} ({diff_guide.get(difficulty, "medium")})

CRITICAL RULES:
- Questions and options in Hindi (Devanagari script)
- Exactly 4 options per question
- Answer field is exactly one of: "A", "B", "C", "D"
- Include 1-2 line explanation in Hindi
- NO trailing commas anywhere
- NO unescaped quotes inside strings
- NO comments
- NO markdown code fences
- Output must be a VALID JSON array

Return ONLY JSON:
[{{"q":"सवाल?","options":["opt1","opt2","opt3","opt4"],"answer":"A","explanation":"कारण"}}]

Generate exactly {count} questions."""

    raw = None
    for attempt, temp in enumerate([0.7, 0.5, 0.3]):
        content = _groq_call(prompt, temp=temp, timeout=120)
        if not content:
            continue
        arr = _extract_json(content, kind="array")
        if arr and isinstance(arr, list) and len(arr) > 0:
            raw = arr
            break

    if not raw:
        return {"error": "Quiz generation failed — try a different topic"}

    cleaned = []
    seen_q = set()
    for q in raw[:count]:
        c = _clean_quiz_question(q, difficulty)
        if not c:
            continue
        key = c["q"].lower()
        if key in seen_q:
            continue
        seen_q.add(key)
        cleaned.append(c)

    if not cleaned:
        return {"error": "No valid questions — try a different topic"}

    preset = DIFFICULTY_PRESETS.get(difficulty, DIFFICULTY_PRESETS["medium"])
    return {
        "ok": True, "topic": topic.title(), "difficulty": difficulty,
        "count": len(cleaned), "time_per_q": preset["time"],
        "hint_available": preset["hint"], "xp_multiplier": preset["xp"],
        "questions": cleaned,
    }


def _format_quiz_question(session_id, index):
    st = _get_quiz(session_id)
    qs = st["questions"]
    if index >= len(qs):
        return _finalize_quiz(session_id)
    q = qs[index]
    letters = ["A", "B", "C", "D"]
    streak_emoji = "🔥" if st.get("streak", 0) >= 3 else ""
    out = (f"## 🧠 Quiz: {st['topic']} · {st['difficulty'].title()}\n\n"
           f"**Q{index + 1}/{len(qs)}** {streak_emoji}\n\n"
           f"{q.get('q', '')}\n\n")
    for i, opt in enumerate(q.get("options", [])):
        out += f"**{letters[i]})** {opt}\n"
    out += (f"\n⏱️ {st.get('time_left', 30)}s · "
            f"💯 Score: {st['score']} · "
            f"🔥 Streak: {st.get('streak', 0)}\n\n"
            f"_**A/B/C/D** · **hint** · **skip** · **quit**_")
    return out


def _finalize_quiz(session_id):
    st = _get_quiz(session_id)
    total = len(st["questions"]) or 1
    score = st["score"]
    pct = int((score / total) * 100)
    if pct >= 90:
        emoji, msg = "🏆", "Outstanding!"
    elif pct >= 75:
        emoji, msg = "🎉", "Excellent!"
    elif pct >= 50:
        emoji, msg = "👍", "Good!"
    else:
        emoji, msg = "📚", "Keep practicing!"
    st["active"] = False
    return (f"## {emoji} Quiz complete!\n\n"
            f"- **Topic:** {st['topic']}\n"
            f"- **Score:** **{score}/{total}** ({pct}%)\n"
            f"- **Max Streak:** 🔥 {st.get('max_streak', 0)}\n"
            f"- **Result:** {msg}\n\n"
            f"_New quiz: `/quiz`_")


def start_quiz(session_id, topic="General Knowledge", difficulty="medium", count=None):
    preset = DIFFICULTY_PRESETS.get(difficulty, DIFFICULTY_PRESETS["medium"])
    if count is None:
        count = preset["count"]
    data = generate_quiz_json(topic, difficulty, count)
    if "error" in data:
        return f"⚠️ {data['error']}"
    with _HISTORY_LOCK:
        _quiz_state[session_id] = {
            "active": True, "topic": data["topic"], "difficulty": data["difficulty"],
            "questions": data["questions"], "current_index": 0, "score": 0,
            "correct": 0, "wrong": 0, "user_answers": [],
            "streak": 0, "max_streak": 0,
            "time_left": data.get("time_per_q", 30),
            "hint_used": False, "hint_available": data.get("hint_available", 1),
            "xp_multiplier": data.get("xp_multiplier", 1.0),
            "question_start": _time.time(),
        }
        _quiz_state.move_to_end(session_id)
        while len(_quiz_state) > MAX_SESSIONS:
            _quiz_state.popitem(last=False)
    return _format_quiz_question(session_id, 0)


def answer_quiz(session_id, user_input):
    st = _get_quiz(session_id)
    if not st["active"]:
        return "No active quiz."
    p = user_input.strip().upper()

    if p in ["QUIT", "STOP", "EXIT"]:
        s, t = st["score"], st["current_index"]
        st["active"] = False
        return f"## ⏹️ Quiz stopped\n\n**Score:** {s}/{t}"

    if p == "HINT":
        if st.get("hint_used"):
            return "Hint already used!"
        if not st.get("hint_available", 1):
            return "Hints not available for this difficulty."
        cur = st["questions"][st["current_index"]]
        correct = str(cur.get("answer", "")).strip().upper()[:1]
        wrongs = [l for l in ["A", "B", "C", "D"] if l != correct]
        _random.shuffle(wrongs)
        st["hint_used"] = True
        return (f"💡 Hint: **{wrongs[0]}** and **{wrongs[1]}** are wrong.\n\n"
                f"{_format_quiz_question(session_id, st['current_index'])}")

    if p == "SKIP":
        cur = st["questions"][st["current_index"]]
        correct = str(cur.get("answer", "")).strip().upper()[:1]
        fb = f"⏭️ **Skipped.** Correct: **{correct}**\n\n"
        if cur.get("explanation"):
            fb += f"💡 _{cur['explanation']}_\n\n"
        st["wrong"] += 1
        st["streak"] = 0
        st["user_answers"].append({"answer": "SKIP", "correct": False})
        st["current_index"] += 1
        if st["current_index"] >= len(st["questions"]):
            return fb + "---\n\n" + _finalize_quiz(session_id)
        st["time_left"] = DIFFICULTY_PRESETS.get(
            st["difficulty"], DIFFICULTY_PRESETS["medium"])["time"]
        st["hint_used"] = False
        st["question_start"] = _time.time()
        return fb + "---\n\n" + _format_quiz_question(session_id, st["current_index"])

    m = re.search(r"\b([A-D])\b", p)
    letter = m.group(1) if m else (p[0] if p and p[0] in "ABCD" else None)
    if not letter:
        return "Reply with **A/B/C/D** · **hint** · **skip** · **quit**"

    cur = st["questions"][st["current_index"]]
    correct = str(cur.get("answer", "")).strip().upper()[:1]
    ok = (letter == correct)
    time_taken = _time.time() - st.get("question_start", _time.time())

    if ok:
        st["score"] += 1
        st["correct"] += 1
        st["streak"] = st.get("streak", 0) + 1
        st["max_streak"] = max(st["max_streak"], st["streak"])
        speed_bonus = max(0, int((st.get("time_left", 30) - time_taken) * 2))
        fb = "✅ **Sahi!** +1"
        if speed_bonus > 0:
            fb += f" ⚡ Speed +{speed_bonus}"
        if st["streak"] >= 3:
            fb += f" 🔥 Streak x{st['streak']}"
        fb += "\n\n"
    else:
        st["wrong"] += 1
        st["streak"] = 0
        fb = f"❌ **Galat.** Correct: **{correct}**\n\n"

    if cur.get("explanation"):
        fb += f"💡 _{cur['explanation']}_\n\n"

    st["user_answers"].append({
        "answer": letter, "correct": ok, "time": round(time_taken, 1),
    })
    st["current_index"] += 1
    if st["current_index"] >= len(st["questions"]):
        return fb + "---\n\n" + _finalize_quiz(session_id)
    st["time_left"] = DIFFICULTY_PRESETS.get(
        st["difficulty"], DIFFICULTY_PRESETS["medium"])["time"]
    st["hint_used"] = False
    st["question_start"] = _time.time()
    return fb + "---\n\n" + _format_quiz_question(session_id, st["current_index"])


def is_quiz_active(session_id):
    return bool(_quiz_state.get(session_id, {}).get("active"))


# ============================================================
# LINGUA (fixed duplicates, expanded)
# ============================================================
LANG_NAMES = {
    "en": "English", "hi": "Hindi", "es": "Spanish", "fr": "French",
    "de": "German", "ja": "Japanese", "ko": "Korean", "zh-CN": "Chinese",
    "ta": "Tamil", "te": "Telugu", "kn": "Kannada", "ml": "Malayalam",
    "bn": "Bengali", "mr": "Marathi", "gu": "Gujarati", "pa": "Punjabi",
    "ur": "Urdu", "sa": "Sanskrit", "ar": "Arabic", "ru": "Russian",
    "pt": "Portuguese", "it": "Italian", "nl": "Dutch", "pl": "Polish",
    "el": "Greek", "sv": "Swedish", "tr": "Turkish", "he": "Hebrew",
    "fa": "Persian", "ne": "Nepali", "si": "Sinhala", "th": "Thai",
    "vi": "Vietnamese", "id": "Indonesian", "no": "Norwegian", "da": "Danish",
    "ga": "Irish", "cy": "Welsh", "gd": "Scottish Gaelic", "eo": "Esperanto",
    "cs": "Czech", "uk": "Ukrainian", "hu": "Hungarian", "fi": "Finnish",
    "ro": "Romanian", "yi": "Yiddish", "la": "Latin", "gl": "Galician",
    "ca": "Catalan", "eu": "Basque", "is": "Icelandic", "sw": "Swahili",
    "ht": "Haitian Creole", "zu": "Zulu", "af": "Afrikaans", "am": "Amharic",
    "ms": "Malay", "tl": "Filipino", "my": "Burmese", "km": "Khmer",
    "nv": "Navajo", "haw": "Hawaiian", "tlh": "Klingon", "val": "High Valyrian",
    # Added new
    "or": "Odia", "as": "Assamese", "sd": "Sindhi", "ks": "Kashmiri",
    "br": "Breton", "mt": "Maltese", "lb": "Luxembourgish", "sq": "Albanian",
}


def generate_lesson(target_lang, from_lang="en", unit_title="Basics",
                    lesson_title="Greetings", level="A1", count=12):
    t_name = LANG_NAMES.get(target_lang, target_lang)
    f_name = LANG_NAMES.get(from_lang, from_lang)
    prompt = f"""You are a language teacher creating a lesson for {f_name} speakers learning {t_name}.
Unit: {unit_title}, Lesson: {lesson_title}, Level: {level}, Exercises: {count}

Return ONLY JSON, no markdown:
{{
  "title": "...",
  "vocab": [{{"word": "...", "translation": "...", "romanization": "...", "example": "..."}}],
  "exercises": [
    {{"type": "mcq", "prompt": "...", "options": ["...", "..."], "answer": "...", "explanation": "..."}},
    {{"type": "translate", "prompt": "...", "answer": "...", "hint": "..."}},
    {{"type": "fill", "prompt": "...", "answer": "...", "hint": "..."}}
  ]
}}

Rules:
- {count} total exercises
- Mix of mcq, translate, fill types
- Match {t_name} script when applicable
- Vocab: 6-10 words with example sentences
"""
    result = _groq_call(prompt, temp=0.7, timeout=120)
    if not result:
        return {"error": "Generation failed"}
    data = _extract_json(result, kind="object")
    if not data:
        return {"error": "Bad format"}
    return {"ok": True, **data}


def generate_units(target_lang, from_lang="en", count=5):
    t_name = LANG_NAMES.get(target_lang, target_lang)
    f_name = LANG_NAMES.get(from_lang, from_lang)
    prompt = f"""Generate course outline for {f_name} speakers learning {t_name}.

Return ONLY JSON:
{{"units": [{{"number": 1, "title": "Greetings", "description": "...", "icon": "👋", "cefr": "A1"}}]}}

Rules: {count} units, A1→A2→B1 progression, emoji icons."""
    result = _groq_call(prompt, temp=0.7)
    if not result:
        return {"error": "Generation failed"}
    data = _extract_json(result, kind="object")
    if not data:
        return {"error": "Bad format"}
    return {"ok": True, "units": data.get("units", [])}


def language_chat(target_lang, user_message, scenario="casual",
                  history=None, from_lang="en"):
    t_name = LANG_NAMES.get(target_lang, target_lang)
    f_name = LANG_NAMES.get(from_lang, from_lang)
    system = f"""You are a friendly native {t_name} speaker helping a {f_name} speaker practice.
Scenario: {scenario}
RULES: Reply in {t_name}, SHORT (1-2 sentences), ask follow-up.

Return ONLY JSON:
{{"reply": "...", "romanization": "...", "translation": "...", "correction": "..."}}"""
    msgs = [{"role": "system", "content": system}]
    for h in (history or [])[-6:]:
        msgs.append({"role": h.get("role", "user"),
                     "content": h.get("content", "")})
    msgs.append({"role": "user", "content": user_message})
    try:
        res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                     "Content-Type": "application/json"},
            json={"model": "openai/gpt-oss-20b", "messages": msgs,
                  "temperature": 0.8},
            timeout=60,
        )
        if res.status_code == 200:
            raw = res.json()["choices"][0]["message"]["content"]
            data = _extract_json(raw, kind="object")
            if data:
                return data
    except Exception as e:
        print(f"[language_chat] {e}", flush=True)
    return {"reply": "...", "translation": "Try again.", "correction": ""}


def extract_vocab_from_text(text, target_lang, from_lang="en", max_words=20):
    t_name = LANG_NAMES.get(target_lang, target_lang)
    f_name = LANG_NAMES.get(from_lang, from_lang)
    prompt = f"""Extract {max_words} vocabulary words from this {t_name} text for a {f_name} learner.
Return ONLY JSON array: [{{"word": "...", "translation": "...", "example": "..."}}]
Text:\n{text[:4000]}"""
    result = _groq_call(prompt, temp=0.3, timeout=90)
    if not result:
        return []
    arr = _extract_json(result, kind="array")
    if not arr or not isinstance(arr, list):
        return []
    return arr[:max_words]


def explain_mistake(exercise, user_answer, target_lang, from_lang="en"):
    t_name = LANG_NAMES.get(target_lang, target_lang)
    prompt = f"""A student learning {t_name} made a mistake.
Exercise: {exercise.get("prompt", "")}
Correct: {exercise.get("answer", "")}
Student's: {user_answer}
Explain in Hinglish (2-3 sentences). Encouraging. Short."""
    result = _groq_call(prompt, temp=0.5, timeout=30)
    return result or "Koi baat nahi! Common mistake. Wapas try karo."


# ============================================================
# VOICE / ROOMS / PEER
# ============================================================
def voice_tutor_reply(topic, user_speech, history=None):
    system = f"""You are NOVEX Voice Tutor — teaching "{topic}" via voice.
RULES: Reply in 1-3 SHORT sentences, ask ONE follow-up question,
match student's language, no markdown."""
    msgs = [{"role": "system", "content": system}]
    for h in (history or [])[-8:]:
        msgs.append({"role": h.get("role", "user"),
                     "content": h.get("content", "")})
    msgs.append({"role": "user", "content": user_speech})
    try:
        res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                     "Content-Type": "application/json"},
            json={"model": "openai/gpt-oss-20b", "messages": msgs,
                  "temperature": 0.8},
            timeout=45,
        )
        if res.status_code == 200:
            return {
                "ok": True,
                "reply": res.json()["choices"][0]["message"]["content"].strip(),
            }
    except Exception as e:
        print(f"[voice_tutor] {e}", flush=True)
    return {"error": "Voice reply failed"}


def generate_room_questions(topic, difficulty="medium", count=10):
    prompt = f"""Generate {count} MCQ for multiplayer quiz.
Topic: {topic}, Difficulty: {difficulty}
Return ONLY JSON array:
[{{"q": "...", "options": ["A","B","C","D"], "answer": "A", "explanation": "..."}}]"""
    result = _groq_call(prompt, temp=0.7, timeout=90)
    if not result:
        return []
    arr = _extract_json(result, kind="array")
    if not arr or not isinstance(arr, list):
        return []
    cleaned = []
    for q in arr[:count]:
        c = _clean_quiz_question(q, difficulty)
        if c:
            cleaned.append({
                "q": c["q"], "options": c["options"],
                "answer": c["answer"], "explanation": c["explanation"],
            })
    return cleaned


def verify_peer_answer(question, student_answer, subject="General"):
    prompt = f"""A student answered another's doubt.
Subject: {subject}
Question: {question}
Answer: {student_answer}

Evaluate in JSON:
{{"rating": 1-5, "is_correct": true/false, "feedback": "1 line", "improvement": "1 line"}}
ONLY JSON."""
    result = _groq_call(prompt, temp=0.5, timeout=45)
    if not result:
        return {"rating": 3, "is_correct": True,
                "feedback": "Looks reasonable!", "improvement": ""}
    data = _extract_json(result, kind="object")
    if data:
        return data
    return {"rating": 3, "is_correct": True, "feedback": "OK", "improvement": ""}


def transcribe_audio_whisper(audio_path, language=None):
    if not GROQ_API_KEY:
        return ""
    try:
        with open(audio_path, "rb") as f:
            files = {"file": (os.path.basename(audio_path), f, "audio/webm")}
            data = {"model": "whisper-large-v3-turbo"}
            if language:
                data["language"] = language
            r = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                files=files, data=data, timeout=60,
            )
            if r.status_code == 200:
                return r.json().get("text", "").strip()
    except Exception as e:
        print(f"[whisper] {e}", flush=True)
    return ""


# ============================================================
# BATCH 1
# ============================================================
def generate_formula_sheet(subject, chapters, board="CBSE"):
    ch_list = ", ".join(chapters) if chapters else "all chapters"
    prompt = f"""Create formula sheet for {board} {subject}. Chapters: {ch_list}

Return ONLY JSON:
{{
  "title": "...",
  "sections": [
    {{"chapter": "...", "formulas": [
      {{"name": "...", "plain": "...", "meaning": "...", "units": "..."}}
    ]}}
  ]
}}
NO markdown outside JSON."""
    result = _groq_call(prompt, temp=0.5, timeout=90)
    if not result:
        return {"error": "Generation failed"}
    data = _extract_json(result, kind="object")
    if not data:
        return {"error": "Bad format"}
    try:
        md = f"# {data.get('title', subject + ' Formula Sheet')}\n\n"
        for sec in data.get("sections", []):
            md += f"## {sec.get('chapter', '')}\n\n"
            md += "| Formula | Meaning | Units |\n|---|---|---|\n"
            for f in sec.get("formulas", []):
                plain = f.get("plain", f.get("latex", ""))
                md += f"| `{plain}` | {f.get('meaning', '')} | {f.get('units', '')} |\n"
            md += "\n"
        return {"ok": True, "title": data.get("title", subject),
                "content": md, "raw": data}
    except Exception as ex:
        return {"error": f"Parse failed: {ex}"}


def generate_mind_map(topic, depth=3):
    prompt = f"""Create hierarchical mind map for: **{topic}**

Return ONLY markdown for Markmap (nested bullet list).
Max depth {depth}, 4-6 main branches.
NO explanations, ONLY markmap markdown."""
    result = _groq_call(prompt, temp=0.5, timeout=60)
    if not result:
        return {"error": "Generation failed"}
    result = result.strip()
    if result.startswith("```"):
        result = re.sub(r"^```(?:markdown|md)?\s*", "", result)
        result = re.sub(r"\s*```$", "", result)
    return {"ok": True, "title": topic, "markdown": result}


def generate_podcast_script(source_text, title="Study Podcast", target_lang="hinglish"):
    prompt = f"""Create 2-minute podcast script from this content.

Return ONLY JSON:
{{"title": "Podcast title", "lines": [{{"speaker": "A", "text": "..."}}, {{"speaker": "B", "text": "..."}}]}}

Rules: A=Teacher, B=Student, Language: {target_lang}, 12-16 lines.

Content:\n{source_text[:3000]}"""
    result = _groq_call(prompt, temp=0.8, timeout=90)
    if not result:
        return {"error": "Generation failed"}
    data = _extract_json(result, kind="object")
    if not data:
        return {"error": "Bad format"}
    return {"ok": True, "title": data.get("title", title),
            "lines": data.get("lines", [])}


def analyze_weak_topics(attempts):
    stats = defaultdict(lambda: {"correct": 0, "total": 0, "subject": "General"})
    for a in attempts:
        topic = a.get("topic", "General")
        stats[topic]["correct"] += a.get("score", 0)
        stats[topic]["total"] += a.get("total", 0)
        stats[topic]["subject"] = a.get("subject", "General")
    weak = []
    for topic, s in stats.items():
        if s["total"] < 3:
            continue
        pct = round((s["correct"] / s["total"]) * 100)
        if pct < 60:
            weak.append({
                "topic": topic, "subject": s["subject"],
                "accuracy": pct, "attempts": s["total"],
                "priority": "high" if pct < 40 else "medium",
            })
    weak.sort(key=lambda x: x["accuracy"])
    return weak[:10]


def debate_generate(topic, round_num, history, side="A"):
    side_label = "supporting" if side == "A" else "opposing"
    system = f"""You are Debater {side} {side_label} "{topic}".
RULES: SHORT (2-3 sentences), facts, counter opponent, persuasive, Hinglish.
Round {round_num}/5."""
    history_text = "\n".join(
        f"[{h.get('speaker', '?')}]: {h.get('content', '')}"
        for h in (history or [])[-6:]
    )
    prompt = f"Topic: {topic}\n\nPrevious:\n{history_text}\n\nNext argument:"
    result = _groq_call(prompt, temp=0.9, timeout=45, system=system)
    return result or "Argument generation failed."


def debate_verdict(topic, history):
    hist = "\n".join(
        f"[{h.get('speaker', '?')}]: {h.get('content', '')}" for h in history
    )
    prompt = f"""Debate on: "{topic}"
Transcript:\n{hist}
As neutral judge, verdict in Hinglish under 150 words."""
    result = _groq_call(prompt, temp=0.7, timeout=60)
    return result or "Debate complete!"


def generate_written_test(topic, qtype="fill_blank", count=5):
    type_map = {
        "true_false": "True/False statements",
        "fill_blank": "Fill in the blank",
        "short_answer": "Short answer",
        "long_answer": "Long answer",
        "match": "Match",
    }
    desc = type_map.get(qtype, "Fill in the blank")
    prompt = f"""Generate {count} {desc} on "{topic}".
Return ONLY JSON array:
[{{"q": "...", "answer": "...", "explanation": "...", "marks": 1}}]"""
    result = _groq_call(prompt, temp=0.7, timeout=60)
    if not result:
        return {"error": "Generation failed"}
    arr = _extract_json(result, kind="array")
    if not arr or not isinstance(arr, list):
        return {"error": "Bad format"}
    return {"ok": True, "topic": topic, "qtype": qtype, "questions": arr[:count]}


def generate_mock_test(exam="JEE Main", subjects=None, count=10, difficulty="medium"):
    subjects = subjects or ["Physics", "Chemistry", "Mathematics"]
    sub_str = ", ".join(subjects)
    prompt = f"""Generate mock test for {exam}.
Subjects: {sub_str}, Count: {count}, Difficulty: {difficulty}

Return ONLY JSON:
{{"exam": "...", "duration_min": 180, "questions": [
  {{"subject": "...", "q": "...", "options": ["A","B","C","D"], "answer": "A",
    "explanation": "...", "marks": 4, "negative": -1}}
]}}"""
    result = _groq_call(prompt, temp=0.7, timeout=120)
    if not result:
        return {"error": "Generation failed"}
    data = _extract_json(result, kind="object")
    if not data:
        return {"error": "Bad format"}
    return {"ok": True, **data}


# ============================================================
# MAIN BRAIN
# ============================================================
_GREETINGS = {
    "hello": "Hey! 👋 Kaise ho?", "hi": "Hi! 😊 Kya haal?",
    "hey": "Hey! Kya chal raha hai?", "hii": "Hi! 😊",
    "hiii": "Hey! Bolo, kya help chahiye?", "namaste": "Namaste! 🙏",
    "namaskar": "Namaskar! 🙏", "good morning": "Good morning! ☀️",
    "gm": "Good morning! ☀️", "good night": "Good night! 🌙",
    "gn": "Good night! 🌙", "bye": "Bye! 👋 Take care.",
    "thanks": "Anytime! 😊", "thank you": "Welcome! 🙌",
    "ok": "👍", "okay": "👍",
}


def novex(user_input, user=None, settings=None, personas=None,
          memory=None, session_id=None):
    sid = session_id or user or "default"
    p = user_input.lower().strip()
    if not p:
        return "Kuch likho toh sahi."
    if p in _GREETINGS:
        return _GREETINGS[p]
    raw_lower = user_input.lower().strip()

    if raw_lower in ("/quiz", "quiz"):
        if _quiz_state.get(sid, {}).get("active"):
            return answer_quiz(sid, user_input)
        return start_quiz(sid, "General Knowledge", "medium")

    if raw_lower in ("/quiz stop", "quiz stop", "/quiz quit", "quiz quit"):
        if _quiz_state.get(sid, {}).get("active"):
            s, t = _quiz_state[sid]["score"], _quiz_state[sid]["current_index"]
            _quiz_state[sid]["active"] = False
            return f"## ⏹️ Quiz stopped\n\n**Score:** {s}/{t}"
        return "Koi quiz active nahi."

    quiz_topic = None
    quiz_diff = "medium"
    for pat in [r"^/quiz\s+(.+)$", r"^quiz\s+on\s+(.+)$",
                r"^start\s+(.+?)\s+quiz$", r"^(.+?)\s+quiz$"]:
        m = re.match(pat, raw_lower)
        if m:
            topic = re.sub(
                r"\s+", " ",
                re.sub(r"\bquiz\b", "", re.sub(r"^/+", "", m.group(1).strip())).strip(),
            ).strip()
            if topic and len(topic) >= 2:
                for diff in ["easy", "medium", "hard", "expert"]:
                    if topic.endswith(" " + diff):
                        quiz_diff = diff
                        topic = topic[:-len(diff)].strip()
                        break
                quiz_topic = topic
                break
    if quiz_topic:
        return start_quiz(sid, quiz_topic.title(), quiz_diff)

    if _quiz_state.get(sid, {}).get("active"):
        return answer_quiz(sid, user_input)

    if p.startswith("model "):
        return set_model(user_input[6:].strip())

    if p.startswith(("translate ", "anuvad ", "अनुवाद ")):
        parts = user_input.split(":", 1)
        if len(parts) == 2:
            target = (parts[0].replace("translate", "").replace("anuvad", "")
                      .replace("अनुवाद", "").replace("to", "").strip())
            result = translate_text(parts[1].strip(), target or "hi", "auto")
            if result.get("ok"):
                return f"**Translation ({target or 'hi'}):**\n\n{result['translated']}"
            return f"⚠️ {result.get('error')}"
        return "**Format:** `translate to hindi: <text>`"

    if _ACTIVE_MODEL.startswith("ollama:"):
        if any(w in p for w in ["time", "samay", "baj", "waqt"]):
            return get_time()
        if any(w in p for w in ["weather", "mausam", "temperature"]):
            city = next((c for c in ["mumbai", "delhi", "bangalore", "kolkata",
                                     "chennai", "pune"] if c in p), "Delhi")
            return get_weather(city)
        if any(w in p for w in ["news", "khabar", "headline"]):
            return get_news()
        if p.startswith("wiki ") or p.startswith("wikipedia "):
            return get_wiki(user_input.split(" ", 1)[1].strip())
        if p.startswith("calc ") or p.startswith("calculate "):
            return calculate(user_input.split(" ", 1)[1])
        return ask_ollama(user_input, model=_ACTIVE_MODEL.replace("ollama:", ""),
                          session_id=sid)

    if p.startswith("mode "):
        mode = p.replace("mode", "").strip()
        if mode in PERSONAS or (personas and mode in personas):
            _current_mode[sid] = mode
            name = personas[mode]["name"] if personas and mode in personas else mode
            return f"✓ Mode: **{name}**"
        return f"Available: **{', '.join(PERSONAS.keys())}**"

    if p in ("save code", "code save karo"):
        if not _last_code.get(sid):
            return "No code yet."
        return save_code(
            _last_code[sid],
            f"novex_code_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.py",
        )

    if p.startswith("pdf "):
        parts = user_input.split(":", 1)
        if len(parts) == 2:
            return ask_about_pdf(parts[0].replace("pdf", "").strip(), parts[1].strip())
        return "**Format:** `pdf <path> : <question>`"

    if p.startswith("note save ") or p.startswith("note likho "):
        return save_note(user_input.split(" ", 2)[-1])
    if p in ("notes", "note dikhao", "mere notes", "show notes"):
        return show_notes()
    if p in ("notes clear", "note delete", "saare notes delete"):
        return clear_notes()

    if p.startswith("calculate ") or p.startswith("calc "):
        return calculate(user_input.split(" ", 1)[1])

    if p.startswith(("wiki ", "wikipedia ")):
        return get_wiki(user_input.split(" ", 1)[1].strip())

    if any(w in p for w in ["kal", "parso", "aaj"]) and \
       any(w in p for w in ["date", "din", "day", "tarikh"]):
        return get_day_info(p)
    if any(w in p for w in ["time", "samay", "baj", "waqt", "clock", "ghadi"]):
        return get_time()

    if any(w in p for w in ["weather", "mausam", "temperature", "garmi",
                            "sardi", "barish", "rain", "forecast"]):
        city = next((c for c in ["mumbai", "delhi", "bangalore", "kolkata",
                                 "chennai", "pune", "hyderabad"] if c in p), "Delhi")
        return get_weather(city)

    if p.startswith(("news ", "khabar ", "khabrein ")):
        topic = re.sub(r"^(news|khabar|khabrein)\s+", "", user_input,
                       flags=re.IGNORECASE).strip()
        return get_news(topic or None)
    if any(w in p for w in ["news", "khabar", "headline"]):
        return get_news()

    if p.startswith(("search ", "google ", "dhundo ", "khojo ", "dhoondo ")):
        q = re.sub(r"^(search|google|dhundo|khojo|dhoondo)\s+", "", user_input,
                   flags=re.IGNORECASE).strip()
        return web_search(q)

    rem = parse_reminder(user_input)
    if rem:
        return f"⏰ Reminder set: **{rem['text']}** @ {rem['when']}"

    return ask_groq(
        user_input,
        custom_instructions=(settings or {}).get("custom_instructions", ""),
        user_personas=personas, memory=memory, session_id=sid,
    )


# ============================================================
# HELPERS
# ============================================================
def get_weather(city="Delhi"):
    try:
        geo = requests.get(
            f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1",
            timeout=10,
        ).json()
        if not geo.get("results"):
            return f"**{city}** nahi mila."
        lat, lon = geo["results"][0]["latitude"], geo["results"][0]["longitude"]
        name = geo["results"][0]["name"]
        c = requests.get(
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,relative_humidity_2m,wind_speed_10m",
            timeout=10,
        ).json()["current"]
        return (f"**{name}**: {c['temperature_2m']}°C, "
                f"humidity {c['relative_humidity_2m']}%, "
                f"wind {c['wind_speed_10m']} km/h")
    except Exception as e:
        return f"Weather error: {e}"


def get_wiki(topic):
    try:
        surl = (f"https://en.wikipedia.org/w/api.php?action=query&list=search"
                f"&srsearch={quote(topic)}&format=json&srlimit=1")
        sr = requests.get(surl, timeout=10).json()
        results = sr.get("query", {}).get("search", [])
        if not results:
            return f"**{topic}** not found."
        title = results[0]["title"]
        res = requests.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(title)}",
            timeout=10,
        )
        if res.status_code == 200:
            ext = res.json().get("extract", "")
            if ext:
                url = f"https://en.wikipedia.org/wiki/{quote(title)}"
                return (f"**{title}**\n\n{ext}\n\n"
                        f"🔗 [Read full article on Wikipedia]({url})")
        return "No summary."
    except Exception as e:
        return f"Wiki error: {e}"


def calculate(expr):
    try:
        allowed = "0123456789+-*/().% "
        if not all(c in allowed for c in expr):
            return "Only numbers and + - * / ( ) allowed."
        r = eval(expr, {"__builtins__": {}}, {})
        return f"`{expr}` = **{r}**"
    except Exception:
        return "Calculation failed."


def save_note(text):
    try:
        with open("notes.txt", "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now(IST).strftime('%d-%m-%Y %H:%M')} — {text}\n")
        return f"✓ Note saved: **{text}**"
    except Exception as e:
        return f"Error: {e}"


def show_notes():
    try:
        with open("notes.txt", "r", encoding="utf-8") as f:
            content = f.read()
        return "**Your notes:**\n\n" + content if content.strip() else "No notes."
    except FileNotFoundError:
        return "No notes."


def clear_notes():
    try:
        open("notes.txt", "w").close()
        return "✓ All notes cleared."
    except Exception as e:
        return f"Error: {e}"


def extract_code(text):
    m = re.findall(r"```(?:\w+)?\n(.*?)```", text, re.DOTALL)
    return m[0] if m else None


def save_code(content, filename="generated.py"):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
        return f"✓ Code saved: **{filename}**"
    except Exception as e:
        return f"Save error: {e}"


def read_pdf(path):
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        return "".join(
            (p.extract_text() or "") + "\n" for p in reader.pages
        ).strip()
    except Exception as e:
        return f"PDF error: {e}"


def ask_about_pdf(path, q):
    text = read_pdf(path)
    if text.startswith("PDF error"):
        return text
    if len(text) > 8000:
        text = text[:8000]
    return ask_groq(f"PDF:\n\n{text}\n\nQ: {q}")


def ask_groq(prompt, system_prompt=None, custom_instructions="", user_personas=None,
             memory=None, session_id="default"):
    mode = _current_mode.get(session_id, "default")
    if system_prompt is None:
        system_prompt = build_system_prompt(
            mode, custom_instructions, user_personas, memory
        )
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}",
               "Content-Type": "application/json"}
    with _HISTORY_LOCK:
        history = list(_chat_history.get(session_id, []))[-6:]
    messages = ([{"role": "system", "content": system_prompt}] + history
                + [{"role": "user", "content": prompt}])
    last_err = ""
    for model in _models_for_call():
        for attempt in range(GROQ_MAX_RETRIES + 1):
            try:
                res = requests.post(
                    url, headers=headers,
                    json={"model": model, "messages": messages, "temperature": 0.8},
                    timeout=GROQ_TIMEOUT,
                )
                if res.status_code == 200:
                    data = res.json()
                    reply = data["choices"][0]["message"]["content"]
                    usage = data.get("usage", {})
                    if usage and _on_usage:
                        try:
                            _on_usage(session_id, model,
                                      usage.get("prompt_tokens", 0),
                                      usage.get("completion_tokens", 0))
                        except Exception:
                            pass
                    with _HISTORY_LOCK:
                        _chat_history.setdefault(session_id, [])
                        _chat_history[session_id].append(
                            {"role": "user", "content": prompt})
                        _chat_history[session_id].append(
                            {"role": "assistant", "content": reply})
                        if len(_chat_history[session_id]) > MAX_HISTORY:
                            _chat_history[session_id][:] = \
                                _chat_history[session_id][-MAX_HISTORY:]
                        _chat_history.move_to_end(session_id)
                        while len(_chat_history) > MAX_SESSIONS:
                            _chat_history.popitem(last=False)
                    code = extract_code(reply)
                    if code:
                        _last_code[session_id] = code
                    return reply
                if res.status_code in (429, 500, 502, 503, 504):
                    last_err = f"{model}: {res.status_code}"
                    _time.sleep(GROQ_RETRY_BACKOFF * (attempt + 1))
                    continue
                last_err = f"{model}: {res.status_code}"
                break
            except Exception as e:
                last_err = f"{model}: {e}"
                _time.sleep(GROQ_RETRY_BACKOFF * (attempt + 1))
    return f"⚠️ All models failed. {last_err}"


def ask_groq_stream(prompt, system_prompt=None, custom_instructions="",
                    user_personas=None, user=None, on_usage=None,
                    memory=None, session_id="default"):
    mode = _current_mode.get(session_id, "default")
    if system_prompt is None:
        system_prompt = build_system_prompt(
            mode, custom_instructions, user_personas, memory
        )
    if not GROQ_API_KEY:
        yield "⚠️ GROQ_API_KEY missing."
        return
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream; charset=utf-8",
    }
    with _HISTORY_LOCK:
        history = list(_chat_history.get(session_id, []))[-6:]
    messages = ([{"role": "system", "content": system_prompt}] + history
                + [{"role": "user", "content": prompt}])
    last_err = ""
    for model in _models_for_call():
        res = None
        try:
            res = requests.post(
                url, headers=headers,
                json={"model": model, "messages": messages,
                      "temperature": 0.8, "stream": True},
                timeout=(10, 90), stream=True,
            )
            if res.status_code != 200:
                last_err = f"{model}: {res.status_code}"
                try:
                    res.close()
                except Exception:
                    pass
                continue

            full = ""
            tokens_in_approx = sum(
                len(str(m.get("content", ""))) // 4 for m in messages
            )
            for raw in res.iter_lines(chunk_size=512, decode_unicode=False):
                if not raw:
                    continue
                try:
                    line = raw.decode("utf-8")
                except UnicodeDecodeError:
                    continue
                if not line.startswith("data: "):
                    continue
                data = line[6:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = _json.loads(data)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        full += content
                        yield content
                except Exception:
                    continue
            try:
                res.close()
            except Exception:
                pass
            if full:
                with _HISTORY_LOCK:
                    _chat_history.setdefault(session_id, [])
                    _chat_history[session_id].append(
                        {"role": "user", "content": prompt})
                    _chat_history[session_id].append(
                        {"role": "assistant", "content": full})
                    if len(_chat_history[session_id]) > MAX_HISTORY:
                        _chat_history[session_id][:] = \
                            _chat_history[session_id][-MAX_HISTORY:]
                    _chat_history.move_to_end(session_id)
                    while len(_chat_history) > MAX_SESSIONS:
                        _chat_history.popitem(last=False)
                code = extract_code(full)
                if code:
                    _last_code[session_id] = code
                cb = on_usage or _on_usage
                if cb and user:
                    try:
                        cb(user, model, tokens_in_approx, len(full) // 4)
                    except Exception:
                        pass
                return
        except Exception as e:
            last_err = f"{model}: {e}"
            if res:
                try:
                    res.close()
                except Exception:
                    pass
            continue
    yield f"⚠️ All models failed. {last_err}"


def ask_ollama(prompt, model="llama3.2", system_prompt=None, session_id="default"):
    if system_prompt is None:
        system_prompt = PERSONAS.get(
            _current_mode.get(session_id, "default"), PERSONAS["default"]
        )
    try:
        res = requests.post(
            "http://localhost:11434/api/chat",
            json={"model": model, "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ], "stream": False},
            timeout=180,
        )
        if res.status_code == 200:
            return res.json()["message"]["content"]
        return f"Ollama error: {res.status_code}"
    except Exception as e:
        return f"Ollama not running ({e})"


def set_model(model_id):
    global _ACTIVE_MODEL
    _ACTIVE_MODEL = model_id
    return f"Model changed: {model_id}"


def get_active_model():
    return _ACTIVE_MODEL


# ============================================================
# HEALTH / DIAGNOSTICS
# ============================================================
def novex_health():
    """Return health info about the backend engine."""
    return {
        "groq_key": bool(GROQ_API_KEY),
        "convex_url": bool(CONVEX_URL),
        "serper_key": bool(SERPER_API_KEY),
        "search_provider": SEARCH_PROVIDER,
        "active_model": _ACTIVE_MODEL,
        "available_models": GROQ_MODELS,
        "vision_models": VISION_MODELS,
        "langs_count": len(LANG_NAMES),
        "personas": list(PERSONAS.keys()),
        "sessions": get_session_info(),
        "search_cache_size": len(_SEARCH_CACHE),
    }


__all__ = [
    # Core
    "novex", "ask_groq", "ask_groq_stream", "ask_ollama",
    "set_model", "get_active_model",
    # Prompts / personas
    "build_system_prompt", "PERSONAS", "DEEP_EXPLAIN_SYSTEM", "DEFAULT_SYSTEM",
    # Session
    "clear_session", "get_session_info", "is_quiz_active",
    # Memory
    "extract_facts",
    # Flashcards / Docs
    "generate_flashcards", "generate_document",
    # Quiz
    "generate_quiz_json", "start_quiz", "answer_quiz",
    "QUIZ_CATEGORIES", "DIFFICULTY_PRESETS",
    # Utils
    "translate_text", "parse_reminder", "get_time", "get_day_info",
    "get_weather", "get_news", "get_wiki", "calculate",
    "save_note", "show_notes", "clear_notes",
    "save_code", "extract_code", "read_pdf", "ask_about_pdf",
    # Search
    "web_search", "web_search_structured", "format_search_results_with_citations",
    # Vision
    "solve_image", "VISION_MODELS",
    # SRS / Gamification
    "srs_next", "calculate_level", "LEVELS", "BADGES", "EXP_REWARDS",
    # Lingua
    "generate_lesson", "generate_units", "language_chat",
    "extract_vocab_from_text", "explain_mistake", "LANG_NAMES",
    # Batch1
    "generate_formula_sheet", "generate_mind_map", "generate_podcast_script",
    "analyze_weak_topics", "debate_generate", "debate_verdict",
    "generate_written_test", "generate_mock_test",
    # Voice / Rooms / Peer
    "voice_tutor_reply", "generate_room_questions",
    "verify_peer_answer", "transcribe_audio_whisper",
    # Health
    "novex_health",
]