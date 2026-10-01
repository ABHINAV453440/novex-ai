import { v } from "convex/values";
import { query, mutation } from "./_generated/server";

// ============================================================
// 🌍 LANGUAGES
// ============================================================
export const listLanguages = query({
  args: { from_lang: v.optional(v.string()) },
  handler: async (ctx, args) => {
    const from = args.from_lang || "en";
    return await ctx.db.query("languages")
      .withIndex("by_from", (q) => q.eq("from_lang", from))
      .filter((q) => q.eq(q.field("active"), true))
      .collect();
  },
});

export const getLanguage = query({
  args: { code: v.string(), from_lang: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db.query("languages")
      .withIndex("by_code_from", (q) =>
        q.eq("code", args.code).eq("from_lang", args.from_lang))
      .first();
  },
});

// ============================================================
// 📚 UNITS
// ============================================================
export const listUnits = query({
  args: { language_code: v.string(), from_lang: v.string() },
  handler: async (ctx, args) => {
    const units = await ctx.db.query("language_units")
      .withIndex("by_language", (q) =>
        q.eq("language_code", args.language_code).eq("from_lang", args.from_lang))
      .collect();
    return units.sort((a, b) => a.unit_number - b.unit_number);
  },
});

// ============================================================
// 📖 LESSONS
// ============================================================
export const getLesson = query({
  args: { unit_id: v.string(), lesson_number: v.number() },
  handler: async (ctx, args) => {
    return await ctx.db.query("language_lessons")
      .withIndex("by_unit_number", (q) =>
        q.eq("unit_id", args.unit_id).eq("lesson_number", args.lesson_number))
      .first();
  },
});

export const listLessonsByUnit = query({
  args: { unit_id: v.string() },
  handler: async (ctx, args) => {
    const lessons = await ctx.db.query("language_lessons")
      .withIndex("by_unit", (q) => q.eq("unit_id", args.unit_id))
      .collect();
    return lessons.sort((a, b) => a.lesson_number - b.lesson_number);
  },
});

export const saveLesson = mutation({
  args: {
    language_code: v.string(), unit_id: v.string(),
    lesson_number: v.number(), title: v.string(),
    exercises_json: v.string(),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db.query("language_lessons")
      .withIndex("by_unit_number", (q) =>
        q.eq("unit_id", args.unit_id).eq("lesson_number", args.lesson_number))
      .first();
    if (existing) {
      await ctx.db.patch(existing._id, {
        exercises_json: args.exercises_json, title: args.title,
      });
      return existing._id;
    }
    return await ctx.db.insert("language_lessons", {
      language_code: args.language_code, unit_id: args.unit_id,
      lesson_number: args.lesson_number, title: args.title,
      exercises_json: args.exercises_json, created: Date.now(),
    });
  },
});

// ============================================================
// 📊 PROGRESS
// ============================================================
export const getUserProgress = query({
  args: { user_id: v.string(), language_code: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db.query("user_language_progress")
      .withIndex("by_user_lang", (q) =>
        q.eq("user_id", args.user_id).eq("language_code", args.language_code))
      .first();
  },
});

export const listUserLanguages = query({
  args: { user_id: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db.query("user_language_progress")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .collect();
  },
});

export const upsertProgress = mutation({
  args: {
    user_id: v.string(), language_code: v.string(), from_lang: v.string(),
    current_unit: v.optional(v.number()), current_lesson: v.optional(v.number()),
    xp_delta: v.optional(v.number()),
    lessons_delta: v.optional(v.number()),
    words_delta: v.optional(v.number()),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db.query("user_language_progress")
      .withIndex("by_user_lang", (q) =>
        q.eq("user_id", args.user_id).eq("language_code", args.language_code))
      .first();
    const now = Date.now();
    const today = new Date().toISOString().slice(0, 10);

    if (!existing) {
      const id = await ctx.db.insert("user_language_progress", {
        user_id: args.user_id, language_code: args.language_code,
        from_lang: args.from_lang,
        current_unit: args.current_unit ?? 1, current_lesson: args.current_lesson ?? 1,
        total_xp: args.xp_delta ?? 0, lessons_completed: args.lessons_delta ?? 0,
        words_learned: args.words_delta ?? 0,
        daily_streak: 1, longest_streak: 1,
        last_practice_date: today, created: now, updated: now,
      });
      return { id, streak: 1, is_new: true };
    }

    let newStreak = existing.daily_streak || 0;
    let longest = existing.longest_streak || 0;
    if (existing.last_practice_date !== today) {
      const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
      if (existing.last_practice_date === yesterday) newStreak += 1;
      else newStreak = 1;
      if (newStreak > longest) longest = newStreak;
    }

    await ctx.db.patch(existing._id, {
      current_unit: args.current_unit ?? existing.current_unit,
      current_lesson: args.current_lesson ?? existing.current_lesson,
      total_xp: (existing.total_xp || 0) + (args.xp_delta || 0),
      lessons_completed: (existing.lessons_completed || 0) + (args.lessons_delta || 0),
      words_learned: (existing.words_learned || 0) + (args.words_delta || 0),
      daily_streak: newStreak, longest_streak: longest,
      last_practice_date: today, updated: now,
    });
    return { id: existing._id, streak: newStreak, is_new: false };
  },
});

// ============================================================
// ✍️ ATTEMPTS
// ============================================================
export const recordAttempt = mutation({
  args: {
    user_id: v.string(), language_code: v.string(),
    lesson_id: v.string(), unit_number: v.number(), lesson_number: v.number(),
    score: v.number(), total: v.number(), time_taken: v.number(),
    mistakes_json: v.string(), xp_gained: v.number(),
  },
  handler: async (ctx, args) => {
    return await ctx.db.insert("user_language_attempts", {
      ...args, created: Date.now(),
    });
  },
});

export const listAttempts = query({
  args: { user_id: v.string(), language_code: v.string(), limit: v.optional(v.number()) },
  handler: async (ctx, args) => {
    const items = await ctx.db.query("user_language_attempts")
      .withIndex("by_user_lang", (q) =>
        q.eq("user_id", args.user_id).eq("language_code", args.language_code))
      .collect();
    return items.sort((a, b) => b.created - a.created).slice(0, args.limit || 20);
  },
});

// ============================================================
// 📚 VOCAB (SRS)
// ============================================================
export const listVocab = query({
  args: { user_id: v.string(), language_code: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db.query("language_vocab")
      .withIndex("by_user_lang", (q) =>
        q.eq("user_id", args.user_id).eq("language_code", args.language_code))
      .collect();
  },
});

export const addVocab = mutation({
  args: {
    user_id: v.string(), language_code: v.string(),
    word: v.string(), translation: v.string(), example: v.string(),
    source: v.string(),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db.query("language_vocab")
      .withIndex("by_user_word", (q) =>
        q.eq("user_id", args.user_id)
         .eq("language_code", args.language_code)
         .eq("word", args.word))
      .first();
    if (existing) return { id: existing._id, duplicate: true };
    const id = await ctx.db.insert("language_vocab", {
      user_id: args.user_id, language_code: args.language_code,
      word: args.word, translation: args.translation, example: args.example,
      ease_factor: 2.5, interval_days: 0, repetitions: 0,
      next_review: Date.now(), source: args.source, created: Date.now(),
    });
    return { id, duplicate: false };
  },
});

export const bulkAddVocab = mutation({
  args: {
    user_id: v.string(), language_code: v.string(),
    words: v.array(v.object({
      word: v.string(), translation: v.string(), example: v.string(),
    })),
    source: v.string(),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db.query("language_vocab")
      .withIndex("by_user_lang", (q) =>
        q.eq("user_id", args.user_id).eq("language_code", args.language_code))
      .collect();
    const existingWords = new Set(existing.map(v => v.word.toLowerCase()));
    const now = Date.now();
    let added = 0;
    for (const w of args.words) {
      if (existingWords.has(w.word.toLowerCase())) continue;
      await ctx.db.insert("language_vocab", {
        user_id: args.user_id, language_code: args.language_code,
        word: w.word, translation: w.translation, example: w.example,
        ease_factor: 2.5, interval_days: 0, repetitions: 0,
        next_review: now, source: args.source, created: now,
      });
      existingWords.add(w.word.toLowerCase());
      added++;
    }
    return { added, skipped: args.words.length - added };
  },
});

export const updateVocabSRS = mutation({
  args: {
    id: v.id("language_vocab"),
    ease_factor: v.number(), interval_days: v.number(),
    repetitions: v.number(), next_review: v.number(),
    last_rating: v.number(),
  },
  handler: async (ctx, args) => {
    const { id, ...patch } = args;
    await ctx.db.patch(id, patch);
    return { ok: true };
  },
});

export const deleteVocab = mutation({
  args: { id: v.id("language_vocab") },
  handler: async (ctx, args) => {
    await ctx.db.delete(args.id);
    return { ok: true };
  },
});

// ============================================================
// 💬 CONVERSATIONS
// ============================================================
export const createConvo = mutation({
  args: {
    user_id: v.string(), language_code: v.string(), scenario: v.string(),
  },
  handler: async (ctx, args) => {
    return await ctx.db.insert("language_convos", {
      user_id: args.user_id, language_code: args.language_code,
      scenario: args.scenario, messages: [], xp_gained: 0,
      created: Date.now(), updated: Date.now(),
    });
  },
});

export const appendConvoMessage = mutation({
  args: {
    convo_id: v.id("language_convos"),
    role: v.string(), content: v.string(),
    translation: v.optional(v.string()),
    correction: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const convo = await ctx.db.get(args.convo_id);
    if (!convo) return { error: "Not found" };
    const messages = [...convo.messages, {
      role: args.role, content: args.content,
      translation: args.translation, correction: args.correction,
      created: Date.now(),
    }];
    await ctx.db.patch(args.convo_id, { messages, updated: Date.now() });
    return { ok: true };
  },
});

export const listConvos = query({
  args: { user_id: v.string(), language_code: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db.query("language_convos")
      .withIndex("by_user_lang", (q) =>
        q.eq("user_id", args.user_id).eq("language_code", args.language_code))
      .collect();
  },
});

export const getConvo = query({
  args: { id: v.id("language_convos") },
  handler: async (ctx, args) => await ctx.db.get(args.id),
});

// ============================================================
// 📖 CURRICULUM + PYQs
// ============================================================
export const listCurriculum = query({
  args: { board: v.string(), class_num: v.number(), subject: v.string() },
  handler: async (ctx, args) => {
    const items = await ctx.db.query("curriculum")
      .withIndex("by_board_class_subject", (q) =>
        q.eq("board", args.board)
         .eq("class_num", args.class_num)
         .eq("subject", args.subject))
      .collect();
    return items.sort((a, b) => a.chapter_num - b.chapter_num);
  },
});

export const listPYQs = query({
  args: {
    exam: v.string(),
    subject: v.optional(v.string()),
    year: v.optional(v.number()),
  },
  handler: async (ctx, args) => {
    const items = await ctx.db.query("pyq_questions")
      .withIndex("by_exam_year", (q) => q.eq("exam", args.exam))
      .collect();
    return items;
  },
});

// ============================================================
// 🌱 SEED MUTATIONS (one-time setup)
// ============================================================
export const seedLanguage = mutation({
  args: {
    code: v.string(), name: v.string(), native_name: v.string(),
    flag: v.string(), from_lang: v.string(), description: v.string(),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db.query("languages")
      .withIndex("by_code_from", (q) =>
        q.eq("code", args.code).eq("from_lang", args.from_lang))
      .first();
    if (existing) return existing._id;
    return await ctx.db.insert("languages", {
      ...args, total_units: 6, active: true, created: Date.now(),
    });
  },
});

export const seedUnit = mutation({
  args: {
    language_code: v.string(), from_lang: v.string(),
    unit_number: v.number(), title: v.string(),
    description: v.string(), icon: v.string(), cefr_level: v.string(),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db.query("language_units")
      .withIndex("by_language_unit", (q) =>
        q.eq("language_code", args.language_code)
         .eq("from_lang", args.from_lang)
         .eq("unit_number", args.unit_number))
      .first();
    if (existing) return existing._id;
    return await ctx.db.insert("language_units", {
      ...args, lessons_count: 6, created: Date.now(),
    });
  },
});