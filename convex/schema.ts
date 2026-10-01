import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

export default defineSchema({
  // ============================================================
  // 👤 USERS & AUTH
  // ============================================================
  users: defineTable({
    username: v.string(),
    email: v.string(),
    password_hash: v.optional(v.string()),
    display_name: v.string(),
    email_verified: v.boolean(),
    auth_provider: v.string(),
    totp_enabled: v.optional(v.boolean()),
    totp_secret: v.optional(v.string()),
    last_login: v.optional(v.number()),
    created: v.number(),
    updated: v.number(),
  })
    .index("by_username", ["username"])
    .index("by_email", ["email"]),

  pending_registrations: defineTable({
    username: v.string(),
    email: v.string(),
    password_hash: v.string(),
    display_name: v.string(),
    code: v.string(),
    expires: v.string(),
    created: v.number(),
  }).index("by_username", ["username"]),

  password_resets: defineTable({
    token: v.string(),
    username: v.string(),
    email: v.string(),
    code: v.string(),
    expires: v.string(),
    created: v.number(),
  })
    .index("by_token", ["token"])
    .index("by_email_code", ["email", "code"]),

  login_history: defineTable({
    user_id: v.string(),
    ip: v.string(),
    ua: v.string(),
    success: v.boolean(),
    time: v.number(),
  }).index("by_user", ["user_id"]),

  // ============================================================
  // 💬 CHATS
  // ============================================================
  chats: defineTable({
    user_id: v.string(),
    title: v.string(),
    project_id: v.optional(v.string()),
    messages: v.array(
      v.object({
        role: v.string(),
        content: v.string(),
        attachments: v.optional(v.array(v.string())),
        sender: v.optional(v.string()),
        created: v.number(),
      })
    ),
    collaborators: v.optional(v.array(v.string())),
    created: v.number(),
    updated: v.number(),
  })
    .index("by_user", ["user_id"])
    .index("by_user_project", ["user_id", "project_id"])
    .index("by_updated", ["updated"]),

  // ============================================================
  // ⚙️ SETTINGS / PERSONAS / PROJECTS / MEMORY
  // ============================================================
  settings: defineTable({
    user_id: v.string(),
    custom_instructions: v.string(),
    quiet_hours: v.object({
      enabled: v.boolean(),
      start: v.string(),
      end: v.string(),
      tz_offset: v.number(),
    }),
    created: v.number(),
    updated: v.number(),
  }).index("by_user", ["user_id"]),

  personas: defineTable({
    user_id: v.string(),
    slug: v.string(),
    name: v.string(),
    prompt: v.string(),
    icon: v.string(),
    created: v.number(),
  })
    .index("by_user", ["user_id"])
    .index("by_user_slug", ["user_id", "slug"]),

  projects: defineTable({
    user_id: v.string(),
    name: v.string(),
    color: v.string(),
    created: v.number(),
    updated: v.number(),
  }).index("by_user", ["user_id"]),

  memory: defineTable({
    user_id: v.string(),
    fact: v.string(),
    source: v.string(),
    created: v.number(),
  })
    .index("by_user", ["user_id"])
    .index("by_user_fact", ["user_id", "fact"]),

  // ============================================================
  // 📚 FLASHCARDS (SRS)
  // ============================================================
  flashcards: defineTable({
    user_id: v.string(),
    title: v.string(),
    cards: v.array(
      v.object({
        front: v.string(),
        back: v.string(),
        ease_factor: v.optional(v.number()),
        interval_days: v.optional(v.number()),
        repetitions: v.optional(v.number()),
        next_review: v.optional(v.number()),
        last_reviewed: v.optional(v.number()),
        last_rating: v.optional(v.number()),
      })
    ),
    reviewed: v.optional(v.number()),
    created: v.number(),
  }).index("by_user", ["user_id"]),

  docs: defineTable({
    user_id: v.string(),
    title: v.string(),
    topic: v.string(),
    style: v.string(),
    length: v.string(),
    language: v.string(),
    outline: v.array(v.string()),
    content: v.string(),
    created: v.number(),
  }).index("by_user", ["user_id"]),

  usage: defineTable({
    user_id: v.string(),
    model: v.string(),
    tokens_in: v.number(),
    tokens_out: v.number(),
    time: v.number(),
  }).index("by_user", ["user_id"]),

  reminders: defineTable({
    user_id: v.string(),
    text: v.string(),
    when_iso: v.string(),
    fired: v.boolean(),
    created: v.number(),
  }).index("by_user", ["user_id"]),

  shared_links: defineTable({
    token: v.string(),
    chat_id: v.string(),
    owner_id: v.string(),
    title: v.string(),
    created: v.number(),
  })
    .index("by_token", ["token"])
    .index("by_owner", ["owner_id"]),

  // ============================================================
  // 🎓 EDUCATION OS
  // ============================================================
  study_plans: defineTable({
    user_id: v.string(),
    title: v.string(),
    exam_name: v.optional(v.string()),
    exam_date: v.optional(v.string()),
    days: v.number(),
    hours_per_day: v.number(),
    subjects: v.array(v.string()),
    plan_json: v.string(),
    created: v.number(),
    updated: v.number(),
  }).index("by_user", ["user_id"]),

  quiz_attempts: defineTable({
    user_id: v.string(),
    topic: v.string(),
    subject: v.string(),
    difficulty: v.string(),
    total: v.number(),
    score: v.number(),
    wrong_topics: v.array(v.string()),
    time_taken: v.number(),
    mode: v.string(),
    created: v.number(),
  }).index("by_user", ["user_id"]),

  streaks: defineTable({
    user_id: v.string(),
    current_streak: v.number(),
    longest_streak: v.number(),
    last_active_date: v.string(),
    total_active_days: v.number(),
    activities: v.array(v.object({ date: v.string(), type: v.string() })),
    created: v.number(),
    updated: v.number(),
  }).index("by_user", ["user_id"]),

  pomodoro_sessions: defineTable({
    user_id: v.string(),
    duration_min: v.number(),
    task: v.string(),
    subject: v.string(),
    date: v.string(),
    created: v.number(),
  }).index("by_user", ["user_id"]),

  classes: defineTable({
    teacher_id: v.string(),
    name: v.string(),
    subject: v.string(),
    description: v.string(),
    class_code: v.string(),
    students: v.array(
      v.object({
        user_id: v.string(),
        username: v.string(),
        display_name: v.string(),
        joined: v.number(),
      })
    ),
    created: v.number(),
    updated: v.number(),
  })
    .index("by_teacher", ["teacher_id"])
    .index("by_code", ["class_code"]),

  assignments: defineTable({
    class_id: v.string(),
    teacher_id: v.string(),
    title: v.string(),
    description: v.string(),
    questions_json: v.string(),
    due_date: v.string(),
    total_marks: v.number(),
    created: v.number(),
    updated: v.number(),
  }).index("by_class", ["class_id"]),

  submissions: defineTable({
    assignment_id: v.string(),
    student_id: v.string(),
    student_name: v.string(),
    answers_json: v.string(),
    grade_json: v.string(),
    score: v.optional(v.number()),
    status: v.string(),
    submitted: v.number(),
    graded: v.optional(v.number()),
    created: v.number(),
  }).index("by_assignment", ["assignment_id"]),

  question_bank: defineTable({
    user_id: v.string(),
    subject: v.string(),
    topic: v.string(),
    qtype: v.string(),
    difficulty: v.string(),
    question_json: v.string(),
    tags: v.array(v.string()),
    created: v.number(),
  }).index("by_user", ["user_id"]),

  class_messages: defineTable({
    class_id: v.string(),
    user_id: v.string(),
    username: v.string(),
    display_name: v.string(),
    role: v.string(),
    content: v.string(),
    created: v.number(),
  }).index("by_class", ["class_id"]),

  attendance: defineTable({
    class_id: v.string(),
    teacher_id: v.string(),
    date: v.string(),
    records: v.array(
      v.object({
        user_id: v.string(),
        display_name: v.string(),
        present: v.boolean(),
      })
    ),
    created: v.number(),
    updated: v.number(),
  })
    .index("by_class", ["class_id"])
    .index("by_class_date", ["class_id", "date"]),

  certificates: defineTable({
    user_id: v.string(),
    title: v.string(),
    recipient_name: v.string(),
    achievement: v.string(),
    issued_by: v.string(),
    cert_json: v.string(),
    issued_at: v.number(),
    created: v.number(),
  }).index("by_user", ["user_id"]),

  study_materials: defineTable({
    class_id: v.string(),
    teacher_id: v.string(),
    title: v.string(),
    description: v.string(),
    file_url: v.string(),
    file_name: v.string(),
    file_type: v.string(),
    file_size: v.number(),
    created: v.number(),
  }).index("by_class", ["class_id"]),

  timetables: defineTable({
    user_id: v.string(),
    title: v.string(),
    scope: v.string(),
    class_id: v.string(),
    timetable_json: v.string(),
    created: v.number(),
    updated: v.number(),
  })
    .index("by_user", ["user_id"])
    .index("by_class", ["class_id"]),

  direct_messages: defineTable({
    from_id: v.string(),
    from_name: v.string(),
    to_id: v.string(),
    to_name: v.string(),
    content: v.string(),
    read: v.boolean(),
    created: v.number(),
  }),

  video_lessons: defineTable({
    class_id: v.string(),
    teacher_id: v.string(),
    title: v.string(),
    description: v.string(),
    video_url: v.string(),
    duration_min: v.number(),
    created: v.number(),
  }).index("by_class", ["class_id"]),

  hall_tickets: defineTable({
    user_id: v.string(),
    exam_name: v.string(),
    exam_date: v.string(),
    exam_time: v.string(),
    duration_min: v.number(),
    center: v.string(),
    subjects: v.array(v.string()),
    roll_prefix: v.string(),
    instructions: v.string(),
    created: v.number(),
  }).index("by_user", ["user_id"]),

  reading_list: defineTable({
    class_id: v.string(),
    teacher_id: v.string(),
    title: v.string(),
    author: v.string(),
    description: v.string(),
    link: v.string(),
    type: v.string(),
    created: v.number(),
  }).index("by_class", ["class_id"]),

  // ============================================================
  // 📸 DOUBT SCANNER
  // ============================================================
  doubt_scans: defineTable({
    user_id: v.string(),
    image_path: v.string(),
    question: v.string(),
    answer: v.string(),
    subject: v.optional(v.string()),
    chat_id: v.optional(v.string()),
    created: v.number(),
  }).index("by_user", ["user_id"]),

  // ============================================================
  // 🏆 GAMIFICATION
  // ============================================================
  user_progress: defineTable({
    user_id: v.string(),
    exp: v.number(),
    level: v.string(),
    level_icon: v.string(),
    quiz_count: v.number(),
    perfect_quizzes: v.number(),
    flashcards_reviewed: v.number(),
    docs_generated: v.number(),
    pomodoros_done: v.number(),
    doubts_solved: v.number(),
    memory_count: v.number(),
    last_daily_bonus: v.optional(v.string()),
    created: v.number(),
    updated: v.number(),
  }).index("by_user", ["user_id"]),

  user_badges: defineTable({
    user_id: v.string(),
    badge_id: v.string(),
    badge_icon: v.string(),
    badge_name: v.string(),
    badge_desc: v.string(),
    unlocked_at: v.number(),
  })
    .index("by_user", ["user_id"])
    .index("by_user_badge", ["user_id", "badge_id"]),

  exp_log: defineTable({
    user_id: v.string(),
    action: v.string(),
    exp_gained: v.number(),
    meta: v.optional(v.string()),
    created: v.number(),
  }).index("by_user", ["user_id"]),

  // ============================================================
  // 🦜 LANGUAGE LEARNING (NOVEX LINGUA)
  // ============================================================
  languages: defineTable({
    code: v.string(),
    name: v.string(),
    native_name: v.string(),
    flag: v.string(),
    from_lang: v.string(),
    total_units: v.number(),
    description: v.string(),
    active: v.boolean(),
    created: v.number(),
  })
    .index("by_code_from", ["code", "from_lang"])
    .index("by_from", ["from_lang"]),

  language_units: defineTable({
    language_code: v.string(),
    from_lang: v.string(),
    unit_number: v.number(),
    title: v.string(),
    description: v.string(),
    icon: v.string(),
    cefr_level: v.string(),
    lessons_count: v.number(),
    created: v.number(),
  })
    .index("by_language", ["language_code", "from_lang"])
    .index("by_language_unit", ["language_code", "from_lang", "unit_number"]),

  language_lessons: defineTable({
    language_code: v.string(),
    unit_id: v.string(),
    lesson_number: v.number(),
    title: v.string(),
    exercises_json: v.string(),
    created: v.number(),
  })
    .index("by_unit", ["unit_id"])
    .index("by_unit_number", ["unit_id", "lesson_number"]),

  user_language_progress: defineTable({
    user_id: v.string(),
    language_code: v.string(),
    from_lang: v.string(),
    current_unit: v.number(),
    current_lesson: v.number(),
    total_xp: v.number(),
    lessons_completed: v.number(),
    words_learned: v.number(),
    daily_streak: v.number(),
    last_practice_date: v.string(),
    longest_streak: v.number(),
    created: v.number(),
    updated: v.number(),
  })
    .index("by_user_lang", ["user_id", "language_code"])
    .index("by_user", ["user_id"]),

  user_language_attempts: defineTable({
    user_id: v.string(),
    language_code: v.string(),
    lesson_id: v.string(),
    unit_number: v.number(),
    lesson_number: v.number(),
    score: v.number(),
    total: v.number(),
    time_taken: v.number(),
    mistakes_json: v.string(),
    xp_gained: v.number(),
    created: v.number(),
  }).index("by_user_lang", ["user_id", "language_code"]),

  language_vocab: defineTable({
    user_id: v.string(),
    language_code: v.string(),
    word: v.string(),
    translation: v.string(),
    example: v.string(),
    ease_factor: v.number(),
    interval_days: v.number(),
    repetitions: v.number(),
    next_review: v.number(),
    last_rating: v.optional(v.number()),
    source: v.string(),
    created: v.number(),
  })
    .index("by_user_lang", ["user_id", "language_code"])
    .index("by_user_word", ["user_id", "language_code", "word"]),

  language_convos: defineTable({
    user_id: v.string(),
    language_code: v.string(),
    scenario: v.string(),
    messages: v.array(
      v.object({
        role: v.string(),
        content: v.string(),
        translation: v.optional(v.string()),
        correction: v.optional(v.string()),
        created: v.number(),
      })
    ),
    xp_gained: v.number(),
    created: v.number(),
    updated: v.number(),
  }).index("by_user_lang", ["user_id", "language_code"]),

  // ============================================================
  // 📖 CURRICULUM + PYQs
  // ============================================================
  curriculum: defineTable({
    board: v.string(),
    class_num: v.number(),
    subject: v.string(),
    chapter_num: v.number(),
    chapter_name: v.string(),
    topics: v.array(v.string()),
    created: v.number(),
  })
    .index("by_board_class", ["board", "class_num"])
    .index("by_board_class_subject", ["board", "class_num", "subject"]),

  pyq_questions: defineTable({
    exam: v.string(),
    year: v.number(),
    subject: v.string(),
    chapter: v.string(),
    question: v.string(),
    options: v.array(v.string()),
    answer: v.string(),
    explanation: v.string(),
    difficulty: v.string(),
    marks: v.number(),
    created: v.number(),
  })
    .index("by_exam_year", ["exam", "year"])
    .index("by_exam_subject", ["exam", "subject"]),

  // ============================================================
  // 🎧 BATCH 1 — PODCASTS, MOCK TESTS, DEBATE, PARENT REPORTS
  // ============================================================
  podcasts: defineTable({
    user_id: v.string(),
    title: v.string(),
    source_text: v.string(),
    script_json: v.string(),
    audio_url: v.string(),
    duration_sec: v.number(),
    created: v.number(),
  }).index("by_user", ["user_id"]),

  mock_tests: defineTable({
    user_id: v.string(),
    exam: v.string(),
    subjects: v.array(v.string()),
    duration_min: v.number(),
    total_questions: v.number(),
    questions_json: v.string(),
    started: v.number(),
    submitted: v.optional(v.number()),
    score: v.optional(v.number()),
    analysis_json: v.optional(v.string()),
    status: v.string(),
    created: v.number(),
  }).index("by_user", ["user_id"]),

  debate_sessions: defineTable({
    user_id: v.string(),
    topic: v.string(),
    rounds: v.number(),
    messages: v.array(
      v.object({
        speaker: v.string(),
        content: v.string(),
        created: v.number(),
      })
    ),
    verdict: v.optional(v.string()),
    created: v.number(),
    updated: v.number(),
  }).index("by_user", ["user_id"]),

  parent_reports: defineTable({
    user_id: v.string(),
    parent_email: v.string(),
    period: v.string(),
    content: v.string(),
    sent: v.boolean(),
    created: v.number(),
  }).index("by_user", ["user_id"]),

  formula_sheets: defineTable({
    user_id: v.string(),
    subject: v.string(),
    chapters: v.array(v.string()),
    content: v.string(),
    created: v.number(),
  }).index("by_user", ["user_id"]),

  mind_maps: defineTable({
    user_id: v.string(),
    title: v.string(),
    source: v.string(),
    markdown: v.string(),
    created: v.number(),
  }).index("by_user", ["user_id"]),

  weak_topics: defineTable({
    user_id: v.string(),
    subject: v.string(),
    topic: v.string(),
    accuracy: v.number(),
    attempts: v.number(),
    last_analyzed: v.number(),
  })
    .index("by_user", ["user_id"])
    .index("by_user_subject", ["user_id", "subject"]),

  // ============================================================
  // 🎙️ BATCH 2 — VOICE TUTOR, ROOMS, AVATAR, PEER DOUBTS, PREFS
  // ============================================================
  voice_sessions: defineTable({
    user_id: v.string(),
    topic: v.string(),
    messages: v.array(
      v.object({
        role: v.string(),
        content: v.string(),
        audio_url: v.optional(v.string()),
        created: v.number(),
      })
    ),
    active: v.boolean(),
    xp_gained: v.number(),
    created: v.number(),
    updated: v.number(),
  }).index("by_user", ["user_id"]),

  study_rooms: defineTable({
    host_id: v.string(),
    host_name: v.string(),
    room_code: v.string(),
    topic: v.string(),
    difficulty: v.string(),
    question_count: v.number(),
    questions_json: v.string(),
    status: v.string(),
    players: v.array(
      v.object({
        user_id: v.string(),
        username: v.string(),
        display_name: v.string(),
        avatar: v.string(),
        score: v.number(),
        answers: v.array(
          v.object({
            idx: v.number(),
            choice: v.string(),
            correct: v.boolean(),
            time_ms: v.number(),
          })
        ),
        joined: v.number(),
        finished: v.boolean(),
      })
    ),
    current_q: v.number(),
    started: v.optional(v.number()),
    ended: v.optional(v.number()),
    created: v.number(),
    updated: v.number(),
  })
    .index("by_code", ["room_code"])
    .index("by_status", ["status"])
    .index("by_host", ["host_id"]),

  user_avatars: defineTable({
    user_id: v.string(),
    emoji: v.string(),
    color: v.string(),
    accessories: v.array(v.string()),
    bg_pattern: v.string(),
    equipped: v.string(),
    updated: v.number(),
  }).index("by_user", ["user_id"]),

  user_unlocks: defineTable({
    user_id: v.string(),
    item_id: v.string(),
    item_type: v.string(),
    unlocked_at: v.number(),
  })
    .index("by_user", ["user_id"])
    .index("by_user_item", ["user_id", "item_id"]),

  peer_doubts: defineTable({
    user_id: v.string(),
    username: v.string(),
    display_name: v.string(),
    avatar: v.string(),
    title: v.string(),
    body: v.string(),
    subject: v.string(),
    topic: v.string(),
    image_url: v.optional(v.string()),
    answers: v.array(
      v.object({
        user_id: v.string(),
        username: v.string(),
        display_name: v.string(),
        avatar: v.string(),
        content: v.string(),
        upvotes: v.number(),
        is_verified: v.boolean(),
        ai_rating: v.optional(v.number()),
        created: v.number(),
      })
    ),
    upvotes: v.number(),
    views: v.number(),
    status: v.string(),
    solved_answer_idx: v.optional(v.number()),
    created: v.number(),
    updated: v.number(),
  })
    .index("by_user", ["user_id"])
    .index("by_subject", ["subject"])
    .index("by_status", ["status"]),

  user_preferences: defineTable({
    user_id: v.string(),
    ui_language: v.string(),
    ai_language: v.string(),
    voice_enabled: v.boolean(),
    voice_speed: v.number(),
    auto_speak: v.boolean(),
    notifications: v.boolean(),
    updated: v.number(),
  }).index("by_user", ["user_id"]),
});