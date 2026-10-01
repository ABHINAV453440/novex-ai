import { query, mutation } from "./_generated/server";
import { v } from "convex/values";
import { Id } from "./_generated/dataModel";

// ============================================================
// 📁 PROJECTS
// ============================================================
export const listProjects = query({
  args: { user_id: v.id("users") },
  handler: async (ctx, args) => {
    return await ctx.db.query("projects")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .collect();
  },
});

export const createProject = mutation({
  args: { user_id: v.id("users"), name: v.string(), color: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db.insert("projects", {
      user_id: args.user_id,
      name: args.name.slice(0, 40),
      color: args.color.slice(0, 9),
      created: Date.now(),
      updated: Date.now(),
    });
  },
});

export const deleteProject = mutation({
  args: { project_id: v.id("projects") },
  handler: async (ctx, args) => {
    const chats = await ctx.db.query("chats").collect();
    for (const c of chats) {
      if (c.project_id === args.project_id) {
        await ctx.db.patch(c._id, { project_id: undefined });
      }
    }
    await ctx.db.delete(args.project_id);
    return { ok: true };
  },
});

// ============================================================
// 🧠 MEMORY
// ============================================================
export const listMemory = query({
  args: { user_id: v.id("users") },
  handler: async (ctx, args) => {
    const items = await ctx.db.query("memory")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .collect();
    return items.sort((a, b) => b.created - a.created);
  },
});

export const addMemory = mutation({
  args: { user_id: v.id("users"), fact: v.string(), source: v.string() },
  handler: async (ctx, args) => {
    const existing = await ctx.db.query("memory")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .collect();
    const dup = existing.find((m) => m.fact.toLowerCase() === args.fact.toLowerCase());
    if (dup) return { id: null, duplicate: true };
    const id = await ctx.db.insert("memory", {
      user_id: args.user_id,
      fact: args.fact.slice(0, 500),
      source: args.source,
      created: Date.now(),
    });
    const all = await ctx.db.query("memory")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .collect();
    if (all.length > 100) {
      const sorted = all.sort((a, b) => a.created - b.created);
      for (let i = 0; i < sorted.length - 100; i++) {
        await ctx.db.delete(sorted[i]._id);
      }
    }
    return { id, duplicate: false };
  },
});

export const deleteMemory = mutation({
  args: { id: v.id("memory") },
  handler: async (ctx, args) => {
    await ctx.db.delete(args.id);
    return { ok: true };
  },
});

export const clearMemory = mutation({
  args: { user_id: v.id("users") },
  handler: async (ctx, args) => {
    const items = await ctx.db.query("memory")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .collect();
    for (const m of items) await ctx.db.delete(m._id);
    return { ok: true };
  },
});

// ============================================================
// 🎭 PERSONAS
// ============================================================
export const listPersonas = query({
  args: { user_id: v.id("users") },
  handler: async (ctx, args) => {
    return await ctx.db.query("personas")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .collect();
  },
});

export const savePersona = mutation({
  args: {
    user_id: v.id("users"),
    slug: v.string(),
    name: v.string(),
    prompt: v.string(),
    icon: v.string(),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db.query("personas")
      .withIndex("by_user_slug", (q) =>
        q.eq("user_id", args.user_id).eq("slug", args.slug))
      .first();
    if (existing) {
      await ctx.db.patch(existing._id, {
        name: args.name,
        prompt: args.prompt.slice(0, 2000),
        icon: args.icon,
      });
      return existing._id;
    }
    return await ctx.db.insert("personas", {
      user_id: args.user_id,
      slug: args.slug,
      name: args.name.slice(0, 30),
      prompt: args.prompt.slice(0, 2000),
      icon: args.icon.slice(0, 4),
      created: Date.now(),
    });
  },
});

export const deletePersona = mutation({
  args: { user_id: v.id("users"), slug: v.string() },
  handler: async (ctx, args) => {
    const entry = await ctx.db.query("personas")
      .withIndex("by_user_slug", (q) =>
        q.eq("user_id", args.user_id).eq("slug", args.slug))
      .first();
    if (entry) await ctx.db.delete(entry._id);
    return { ok: true };
  },
});

// ============================================================
// 📚 FLASHCARDS
// ============================================================
export const listFlashcards = query({
  args: { user_id: v.id("users") },
  handler: async (ctx, args) => {
    return await ctx.db.query("flashcards")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .collect();
  },
});

export const createFlashcardDeck = mutation({
  args: {
    user_id: v.id("users"),
    title: v.string(),
    cards: v.array(v.object({ front: v.string(), back: v.string() })),
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    const enriched = args.cards.map((c) => ({
      front: c.front,
      back: c.back,
      ease_factor: 2.5,
      interval_days: 0,
      repetitions: 0,
      next_review: now,
    }));
    return await ctx.db.insert("flashcards", {
      user_id: args.user_id,
      title: args.title.slice(0, 60),
      cards: enriched,
      created: now,
      reviewed: 0,
    });
  },
});

export const updateFlashcardDeck = mutation({
  args: {
    id: v.id("flashcards"),
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
    reviewed: v.number(),
  },
  handler: async (ctx, args) => {
    await ctx.db.patch(args.id, { cards: args.cards, reviewed: args.reviewed });
    return { ok: true };
  },
});

export const deleteFlashcardDeck = mutation({
  args: { id: v.id("flashcards") },
  handler: async (ctx, args) => {
    await ctx.db.delete(args.id);
    return { ok: true };
  },
});

// ============================================================
// 📝 DOCS
// ============================================================
export const listDocs = query({
  args: { user_id: v.id("users") },
  handler: async (ctx, args) => {
    const docs = await ctx.db.query("docs")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .collect();
    return docs.map((d) => ({
      id: d._id,
      title: d.title,
      created: d.created,
      length: d.content.length,
    }));
  },
});

export const getDoc = query({
  args: { id: v.id("docs") },
  handler: async (ctx, args) => await ctx.db.get(args.id),
});

export const createDoc = mutation({
  args: {
    user_id: v.id("users"),
    title: v.string(),
    topic: v.string(),
    style: v.string(),
    length: v.string(),
    language: v.string(),
    outline: v.array(v.string()),
    content: v.string(),
  },
  handler: async (ctx, args) => {
    return await ctx.db.insert("docs", {
      user_id: args.user_id,
      title: args.title.slice(0, 80),
      topic: args.topic,
      style: args.style,
      length: args.length,
      language: args.language,
      outline: args.outline,
      content: args.content,
      created: Date.now(),
    });
  },
});

export const deleteDoc = mutation({
  args: { id: v.id("docs") },
  handler: async (ctx, args) => {
    await ctx.db.delete(args.id);
    return { ok: true };
  },
});

// ============================================================
// ⚙️ SETTINGS
// ============================================================
export const getSettings = query({
  args: { user_id: v.id("users") },
  handler: async (ctx, args) => {
    const s = await ctx.db.query("settings")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .first();
    if (!s) {
      return {
        custom_instructions: "",
        quiet_hours: { enabled: false, start: "22:00", end: "07:00", tz_offset: 5.5 },
      };
    }
    return s;
  },
});

export const updateSettings = mutation({
  args: {
    user_id: v.id("users"),
    custom_instructions: v.optional(v.string()),
    quiet_hours: v.optional(
      v.object({
        enabled: v.boolean(),
        start: v.string(),
        end: v.string(),
        tz_offset: v.number(),
      })
    ),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db.query("settings")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .first();
    const patch: any = { updated: Date.now() };
    if (args.custom_instructions !== undefined) {
      patch.custom_instructions = args.custom_instructions.slice(0, 4000);
    }
    if (args.quiet_hours !== undefined) patch.quiet_hours = args.quiet_hours;
    if (existing) {
      await ctx.db.patch(existing._id, patch);
      return existing._id;
    } else {
      return await ctx.db.insert("settings", {
        user_id: args.user_id,
        custom_instructions: patch.custom_instructions || "",
        quiet_hours: patch.quiet_hours || {
          enabled: false,
          start: "22:00",
          end: "07:00",
          tz_offset: 5.5,
        },
        created: Date.now(),
        updated: Date.now(),
      });
    }
  },
});

// ============================================================
// 📊 STATS
// ============================================================
export const getStats = query({
  args: { user_id: v.id("users") },
  handler: async (ctx, args) => {
    const items = await ctx.db.query("usage")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .collect();
    if (!items.length) {
      return { total_in: 0, total_out: 0, calls: 0, model_stats: [] };
    }
    let total_in = 0;
    let total_out = 0;
    const modelMap: Record<string, any> = {};
    for (const u of items) {
      total_in += u.tokens_in;
      total_out += u.tokens_out;
      const key = u.model;
      if (!modelMap[key]) {
        modelMap[key] = { model: key, in: 0, out: 0, calls: 0 };
      }
      modelMap[key].in += u.tokens_in;
      modelMap[key].out += u.tokens_out;
      modelMap[key].calls += 1;
    }
    return {
      total_in,
      total_out,
      calls: items.length,
      model_stats: Object.values(modelMap),
    };
  },
});

export const recordUsage = mutation({
  args: {
    user_id: v.id("users"),
    model: v.string(),
    tokens_in: v.number(),
    tokens_out: v.number(),
  },
  handler: async (ctx, args) => {
    return await ctx.db.insert("usage", {
      user_id: args.user_id,
      model: args.model,
      tokens_in: args.tokens_in,
      tokens_out: args.tokens_out,
      time: Date.now(),
    });
  },
});

// ============================================================
// ⏰ REMINDERS
// ============================================================
export const listReminders = query({
  args: { user_id: v.id("users") },
  handler: async (ctx, args) => {
    return await ctx.db.query("reminders")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .collect();
  },
});

export const createReminder = mutation({
  args: { user_id: v.id("users"), text: v.string(), when_iso: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db.insert("reminders", {
      user_id: args.user_id,
      text: args.text,
      when_iso: args.when_iso,
      created: Date.now(),
      fired: false,
    });
  },
});

export const deleteReminder = mutation({
  args: { id: v.id("reminders") },
  handler: async (ctx, args) => {
    await ctx.db.delete(args.id);
    return { ok: true };
  },
});

// ============================================================
// 🔗 SHARED LINKS
// ============================================================
export const createSharedLink = mutation({
  args: {
    token: v.string(),
    chat_id: v.id("chats"),
    owner_id: v.id("users"),
    title: v.string(),
  },
  handler: async (ctx, args) => {
    return await ctx.db.insert("shared_links", {
      token: args.token,
      chat_id: args.chat_id,
      owner_id: args.owner_id,
      title: args.title,
      created: Date.now(),
    });
  },
});

export const getSharedLink = query({
  args: { token: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db.query("shared_links")
      .withIndex("by_token", (q) => q.eq("token", args.token))
      .first();
  },
});

// ============================================================
// 🎯 GAMIFICATION
// ============================================================
export const getProgress = query({
  args: { user_id: v.id("users") },
  handler: async (ctx, args) => {
    return await ctx.db.query("user_progress")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .first();
  },
});

export const createProgress = mutation({
  args: { user_id: v.id("users") },
  handler: async (ctx, args) => {
    const now = Date.now();
    return await ctx.db.insert("user_progress", {
      user_id: args.user_id,
      exp: 0,
      level: "Beginner",
      level_icon: "🌱",
      quiz_count: 0,
      perfect_quizzes: 0,
      flashcards_reviewed: 0,
      docs_generated: 0,
      pomodoros_done: 0,
      doubts_solved: 0,
      memory_count: 0,
      created: now,
      updated: now,
    });
  },
});

export const updateProgress = mutation({
  args: {
    user_id: v.id("users"),
    exp: v.number(),
    level: v.string(),
    level_icon: v.string(),
  },
  handler: async (ctx, args) => {
    const p = await ctx.db.query("user_progress")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .first();
    if (!p) return { ok: false };
    await ctx.db.patch(p._id, {
      exp: args.exp,
      level: args.level,
      level_icon: args.level_icon,
      updated: Date.now(),
    });
    return { ok: true };
  },
});

export const incrementCounter = mutation({
  args: {
    user_id: v.id("users"),
    field: v.string(),
    amount: v.number(),
  },
  handler: async (ctx, args) => {
    const p = await ctx.db.query("user_progress")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .first();
    if (!p) return { ok: false };
    const allowed = [
      "quiz_count",
      "perfect_quizzes",
      "flashcards_reviewed",
      "docs_generated",
      "pomodoros_done",
      "doubts_solved",
      "memory_count",
    ];
    if (!allowed.includes(args.field)) return { ok: false };
    const cur = (p as any)[args.field] || 0;
    await ctx.db.patch(p._id, {
      [args.field]: cur + args.amount,
      updated: Date.now(),
    });
    return { ok: true };
  },
});

export const listBadges = query({
  args: { user_id: v.id("users") },
  handler: async (ctx, args) => {
    return await ctx.db.query("user_badges")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .collect();
  },
});

export const unlockBadge = mutation({
  args: {
    user_id: v.id("users"),
    badge_id: v.string(),
    badge_icon: v.string(),
    badge_name: v.string(),
    badge_desc: v.string(),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db.query("user_badges")
      .withIndex("by_user_badge", (q) =>
        q.eq("user_id", args.user_id).eq("badge_id", args.badge_id))
      .first();
    if (existing) return { ok: false, already: true };
    const id = await ctx.db.insert("user_badges", {
      user_id: args.user_id,
      badge_id: args.badge_id,
      badge_icon: args.badge_icon,
      badge_name: args.badge_name,
      badge_desc: args.badge_desc,
      unlocked_at: Date.now(),
    });
    return { ok: true, id };
  },
});

export const logExp = mutation({
  args: {
    user_id: v.id("users"),
    action: v.string(),
    exp_gained: v.number(),
    meta: v.string(),
  },
  handler: async (ctx, args) => {
    return await ctx.db.insert("exp_log", {
      user_id: args.user_id,
      action: args.action,
      exp_gained: args.exp_gained,
      meta: args.meta,
      created: Date.now(),
    });
  },
});

// ============================================================
// 📋 BATCH 1 — FORMULA SHEETS
// ============================================================
export const createFormulaSheet = mutation({
  args: {
    user_id: v.id("users"),
    subject: v.string(),
    chapters: v.array(v.string()),
    content: v.string(),
  },
  handler: async (ctx, args) => {
    return await ctx.db.insert("formula_sheets", {
      ...args,
      created: Date.now(),
    });
  },
});

export const listFormulaSheets = query({
  args: { user_id: v.id("users") },
  handler: async (ctx, args) => {
    return await ctx.db.query("formula_sheets")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .collect();
  },
});

export const deleteFormulaSheet = mutation({
  args: { id: v.id("formula_sheets") },
  handler: async (ctx, args) => {
    await ctx.db.delete(args.id);
    return { ok: true };
  },
});

// ============================================================
// 🧠 BATCH 1 — MIND MAPS
// ============================================================
export const createMindMap = mutation({
  args: {
    user_id: v.id("users"),
    title: v.string(),
    source: v.string(),
    markdown: v.string(),
  },
  handler: async (ctx, args) => {
    return await ctx.db.insert("mind_maps", {
      ...args,
      created: Date.now(),
    });
  },
});

export const listMindMaps = query({
  args: { user_id: v.id("users") },
  handler: async (ctx, args) => {
    return await ctx.db.query("mind_maps")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .collect();
  },
});

export const deleteMindMap = mutation({
  args: { id: v.id("mind_maps") },
  handler: async (ctx, args) => {
    await ctx.db.delete(args.id);
    return { ok: true };
  },
});

// ============================================================
// 🎧 BATCH 1 — PODCASTS
// ============================================================
export const createPodcast = mutation({
  args: {
    user_id: v.id("users"),
    title: v.string(),
    source_text: v.string(),
    script_json: v.string(),
    audio_url: v.string(),
    duration_sec: v.number(),
  },
  handler: async (ctx, args) => {
    return await ctx.db.insert("podcasts", {
      ...args,
      created: Date.now(),
    });
  },
});

export const listPodcasts = query({
  args: { user_id: v.id("users") },
  handler: async (ctx, args) => {
    return await ctx.db.query("podcasts")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .collect();
  },
});

export const deletePodcast = mutation({
  args: { id: v.id("podcasts") },
  handler: async (ctx, args) => {
    await ctx.db.delete(args.id);
    return { ok: true };
  },
});

// ============================================================
// 🎭 BATCH 1 — DEBATES
// ============================================================
export const createDebate = mutation({
  args: {
    user_id: v.id("users"),
    topic: v.string(),
    rounds: v.number(),
  },
  handler: async (ctx, args) => {
    return await ctx.db.insert("debate_sessions", {
      ...args,
      messages: [],
      created: Date.now(),
      updated: Date.now(),
    });
  },
});

export const appendDebateMessage = mutation({
  args: {
    debate_id: v.id("debate_sessions"),
    speaker: v.string(),
    content: v.string(),
  },
  handler: async (ctx, args) => {
    const d = await ctx.db.get(args.debate_id);
    if (!d) return { ok: false };
    const messages = [
      ...d.messages,
      { speaker: args.speaker, content: args.content, created: Date.now() },
    ];
    await ctx.db.patch(args.debate_id, { messages, updated: Date.now() });
    return { ok: true };
  },
});

export const setDebateVerdict = mutation({
  args: { debate_id: v.id("debate_sessions"), verdict: v.string() },
  handler: async (ctx, args) => {
    await ctx.db.patch(args.debate_id, {
      verdict: args.verdict,
      updated: Date.now(),
    });
    return { ok: true };
  },
});

// ============================================================
// ⏱️ BATCH 1 — MOCK TESTS
// ============================================================
export const createMockTest = mutation({
  args: {
    user_id: v.id("users"),
    exam: v.string(),
    subjects: v.array(v.string()),
    duration_min: v.number(),
    total_questions: v.number(),
    questions_json: v.string(),
  },
  handler: async (ctx, args) => {
    return await ctx.db.insert("mock_tests", {
      ...args,
      started: Date.now(),
      status: "active",
      created: Date.now(),
    });
  },
});

export const getMockTest = query({
  args: { id: v.id("mock_tests") },
  handler: async (ctx, args) => await ctx.db.get(args.id),
});

export const submitMockTest = mutation({
  args: {
    id: v.id("mock_tests"),
    score: v.number(),
    analysis_json: v.string(),
  },
  handler: async (ctx, args) => {
    await ctx.db.patch(args.id, {
      score: args.score,
      analysis_json: args.analysis_json,
      submitted: Date.now(),
      status: "submitted",
    });
    return { ok: true };
  },
});

export const listMockTests = query({
  args: { user_id: v.id("users") },
  handler: async (ctx, args) => {
    return await ctx.db.query("mock_tests")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .collect();
  },
});

// ============================================================
// 👨‍👩‍👧 BATCH 1 — PARENT REPORTS
// ============================================================
export const createParentReport = mutation({
  args: {
    user_id: v.id("users"),
    parent_email: v.string(),
    period: v.string(),
    content: v.string(),
    sent: v.boolean(),
  },
  handler: async (ctx, args) => {
    return await ctx.db.insert("parent_reports", {
      ...args,
      created: Date.now(),
    });
  },
});

export const getParentReport = query({
  args: { id: v.id("parent_reports") },
  handler: async (ctx, args) => await ctx.db.get(args.id),
});

export const markParentReportSent = mutation({
  args: { id: v.id("parent_reports") },
  handler: async (ctx, args) => {
    await ctx.db.patch(args.id, { sent: true });
    return { ok: true };
  },
});

// ============================================================
// 🎙️ BATCH 2 — VOICE SESSIONS
// ============================================================
export const createVoiceSession = mutation({
  args: { user_id: v.id("users"), topic: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db.insert("voice_sessions", {
      user_id: args.user_id,
      topic: args.topic,
      messages: [],
      active: true,
      xp_gained: 0,
      created: Date.now(),
      updated: Date.now(),
    });
  },
});

export const getVoiceSession = query({
  args: { id: v.id("voice_sessions") },
  handler: async (ctx, args) => await ctx.db.get(args.id),
});

export const appendVoiceMessage = mutation({
  args: {
    session_id: v.id("voice_sessions"),
    role: v.string(),
    content: v.string(),
  },
  handler: async (ctx, args) => {
    const s = await ctx.db.get(args.session_id);
    if (!s) return { ok: false };
    const messages = [
      ...s.messages,
      { role: args.role, content: args.content, created: Date.now() },
    ];
    await ctx.db.patch(args.session_id, { messages, updated: Date.now() });
    return { ok: true };
  },
});

export const endVoiceSession = mutation({
  args: { session_id: v.id("voice_sessions") },
  handler: async (ctx, args) => {
    await ctx.db.patch(args.session_id, { active: false, updated: Date.now() });
    return { ok: true };
  },
});

// ============================================================
// 👥 BATCH 2 — STUDY ROOMS
// ============================================================
export const createStudyRoom = mutation({
  args: {
    host_id: v.id("users"),
    host_name: v.string(),
    room_code: v.string(),
    topic: v.string(),
    difficulty: v.string(),
    question_count: v.number(),
    questions_json: v.string(),
    avatar: v.string(),
  },
  handler: async (ctx, args) => {
    return await ctx.db.insert("study_rooms", {
      host_id: args.host_id,
      host_name: args.host_name,
      room_code: args.room_code,
      topic: args.topic,
      difficulty: args.difficulty,
      question_count: args.question_count,
      questions_json: args.questions_json,
      status: "waiting",
      players: [
        {
          user_id: args.host_id,
          username: args.host_name,
          display_name: args.host_name,
          avatar: args.avatar,
          score: 0,
          answers: [],
          joined: Date.now(),
          finished: false,
        },
      ],
      current_q: 0,
      created: Date.now(),
      updated: Date.now(),
    });
  },
});

export const getStudyRoom = query({
  args: { id: v.id("study_rooms") },
  handler: async (ctx, args) => await ctx.db.get(args.id),
});

export const getRoomByCode = query({
  args: { code: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db.query("study_rooms")
      .withIndex("by_code", (q) => q.eq("room_code", args.code))
      .first();
  },
});

export const joinStudyRoom = mutation({
  args: {
    room_id: v.id("study_rooms"),
    user_id: v.id("users"),
    username: v.string(),
    display_name: v.string(),
    avatar: v.string(),
  },
  handler: async (ctx, args) => {
    const room = await ctx.db.get(args.room_id);
    if (!room) return { error: "Not found" };
    const players = [...room.players];
    if (players.some((p) => p.user_id === args.user_id)) return { already: true };
    players.push({
      user_id: args.user_id,
      username: args.username,
      display_name: args.display_name,
      avatar: args.avatar,
      score: 0,
      answers: [],
      joined: Date.now(),
      finished: false,
    });
    await ctx.db.patch(args.room_id, { players, updated: Date.now() });
    return { ok: true };
  },
});

export const startStudyRoom = mutation({
  args: { room_id: v.id("study_rooms") },
  handler: async (ctx, args) => {
    await ctx.db.patch(args.room_id, {
      status: "active",
      current_q: 0,
      started: Date.now(),
      updated: Date.now(),
    });
    return { ok: true };
  },
});

export const submitRoomAnswer = mutation({
  args: {
    room_id: v.id("study_rooms"),
    user_id: v.string(),
    idx: v.number(),
    choice: v.string(),
    time_ms: v.number(),
  },
  handler: async (ctx, args) => {
    const room = await ctx.db.get(args.room_id);
    if (!room) return { error: "Not found" };
    const questions = JSON.parse(room.questions_json);
    const q = questions[args.idx];
    if (!q) return { error: "Invalid idx" };
    const correct = args.choice === q.answer;
    const players = room.players.map((p) => {
      if (p.user_id !== args.user_id) return p;
      return {
        ...p,
        score: p.score + (correct ? 10 : 0),
        answers: [
          ...p.answers,
          {
            idx: args.idx,
            choice: args.choice,
            correct,
            time_ms: args.time_ms,
          },
        ],
      };
    });
    await ctx.db.patch(args.room_id, { players, updated: Date.now() });
    return { correct, answer: q.answer, explanation: q.explanation };
  },
});

export const nextRoomQuestion = mutation({
  args: { room_id: v.id("study_rooms") },
  handler: async (ctx, args) => {
    const room = await ctx.db.get(args.room_id);
    if (!room) return { error: "Not found" };
    const next = room.current_q + 1;
    const finished = next >= room.question_count;
    await ctx.db.patch(args.room_id, {
      current_q: next,
      status: finished ? "finished" : "active",
      ended: finished ? Date.now() : undefined,
      updated: Date.now(),
    });
    return { next, finished };
  },
});

export const leaveStudyRoom = mutation({
  args: { room_id: v.id("study_rooms"), user_id: v.string() },
  handler: async (ctx, args) => {
    const room = await ctx.db.get(args.room_id);
    if (!room) return { ok: false };
    const players = room.players.filter((p) => p.user_id !== args.user_id);
    await ctx.db.patch(args.room_id, { players, updated: Date.now() });
    return { ok: true };
  },
});

// ============================================================
// 🎨 BATCH 2 — AVATARS
// ============================================================
export const getAvatar = query({
  args: { user_id: v.id("users") },
  handler: async (ctx, args) => {
    return await ctx.db.query("user_avatars")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .first();
  },
});

export const createAvatar = mutation({
  args: { user_id: v.id("users") },
  handler: async (ctx, args) => {
    return await ctx.db.insert("user_avatars", {
      user_id: args.user_id,
      emoji: "🎓",
      color: "#10a37f",
      accessories: [],
      bg_pattern: "solid",
      equipped: "",
      updated: Date.now(),
    });
  },
});

export const updateAvatar = mutation({
  args: {
    user_id: v.id("users"),
    emoji: v.optional(v.string()),
    color: v.optional(v.string()),
    bg_pattern: v.optional(v.string()),
    equipped: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const av = await ctx.db.query("user_avatars")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .first();
    if (!av) return { ok: false };
    const patch: any = { updated: Date.now() };
    for (const k of ["emoji", "color", "bg_pattern", "equipped"]) {
      if ((args as any)[k] !== undefined) patch[k] = (args as any)[k];
    }
    await ctx.db.patch(av._id, patch);
    return { ok: true };
  },
});

export const listUnlocks = query({
  args: { user_id: v.id("users") },
  handler: async (ctx, args) => {
    return await ctx.db.query("user_unlocks")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .collect();
  },
});

export const unlockItem = mutation({
  args: {
    user_id: v.id("users"),
    item_id: v.string(),
    item_type: v.string(),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db.query("user_unlocks")
      .withIndex("by_user_item", (q) =>
        q.eq("user_id", args.user_id).eq("item_id", args.item_id))
      .first();
    if (existing) return { duplicate: true };
    const id = await ctx.db.insert("user_unlocks", {
      user_id: args.user_id,
      item_id: args.item_id,
      item_type: args.item_type,
      unlocked_at: Date.now(),
    });
    return { id };
  },
});

// ============================================================
// 📚 BATCH 2 — PEER DOUBTS
// ============================================================
export const listPeerDoubts = query({
  args: { subject: v.string(), status: v.string() },
  handler: async (ctx, args) => {
    const items = await ctx.db.query("peer_doubts").collect();
    let filtered = items;
    if (args.status) filtered = filtered.filter((d) => d.status === args.status);
    if (args.subject) filtered = filtered.filter((d) => d.subject === args.subject);
    return filtered.sort((a, b) => b.created - a.created);
  },
});

export const getPeerDoubt = query({
  args: { id: v.id("peer_doubts") },
  handler: async (ctx, args) => await ctx.db.get(args.id),
});

export const createPeerDoubt = mutation({
  args: {
    user_id: v.id("users"),
    username: v.string(),
    display_name: v.string(),
    avatar: v.string(),
    title: v.string(),
    body: v.string(),
    subject: v.string(),
    topic: v.string(),
    image_url: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    return await ctx.db.insert("peer_doubts", {
      ...args,
      answers: [],
      upvotes: 0,
      views: 0,
      status: "open",
      created: Date.now(),
      updated: Date.now(),
    });
  },
});

export const addPeerAnswer = mutation({
  args: {
    doubt_id: v.id("peer_doubts"),
    user_id: v.string(),
    username: v.string(),
    display_name: v.string(),
    avatar: v.string(),
    content: v.string(),
    is_verified: v.boolean(),
    ai_rating: v.number(),
  },
  handler: async (ctx, args) => {
    const d = await ctx.db.get(args.doubt_id);
    if (!d) return { error: "Not found" };
    const answers = [
      ...d.answers,
      {
        user_id: args.user_id,
        username: args.username,
        display_name: args.display_name,
        avatar: args.avatar,
        content: args.content,
        upvotes: 0,
        is_verified: args.is_verified,
        ai_rating: args.ai_rating,
        created: Date.now(),
      },
    ];
    await ctx.db.patch(args.doubt_id, { answers, updated: Date.now() });
    return { ok: true };
  },
});

export const upvotePeerDoubt = mutation({
  args: { doubt_id: v.id("peer_doubts") },
  handler: async (ctx, args) => {
    const d = await ctx.db.get(args.doubt_id);
    if (!d) return { ok: false };
    await ctx.db.patch(args.doubt_id, { upvotes: d.upvotes + 1 });
    return { ok: true };
  },
});

export const markDoubtSolved = mutation({
  args: { doubt_id: v.id("peer_doubts"), answer_idx: v.number() },
  handler: async (ctx, args) => {
    await ctx.db.patch(args.doubt_id, {
      status: "solved",
      solved_answer_idx: args.answer_idx,
      updated: Date.now(),
    });
    return { ok: true };
  },
});

// ============================================================
// 🌍 BATCH 2 — PREFERENCES
// ============================================================
export const getPreferences = query({
  args: { user_id: v.id("users") },
  handler: async (ctx, args) => {
    return await ctx.db.query("user_preferences")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .first();
  },
});

export const createPreferences = mutation({
  args: { user_id: v.id("users") },
  handler: async (ctx, args) => {
    return await ctx.db.insert("user_preferences", {
      user_id: args.user_id,
      ui_language: "en",
      ai_language: "hinglish",
      voice_enabled: true,
      voice_speed: 1.0,
      auto_speak: false,
      notifications: true,
      updated: Date.now(),
    });
  },
});

export const updatePreferences = mutation({
  args: {
    user_id: v.id("users"),
    ui_language: v.optional(v.string()),
    ai_language: v.optional(v.string()),
    voice_enabled: v.optional(v.boolean()),
    voice_speed: v.optional(v.number()),
    auto_speak: v.optional(v.boolean()),
    notifications: v.optional(v.boolean()),
  },
  handler: async (ctx, args) => {
    const p = await ctx.db.query("user_preferences")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .first();
    if (!p) return { ok: false };
    const patch: any = { updated: Date.now() };
    for (const k of [
      "ui_language",
      "ai_language",
      "voice_enabled",
      "voice_speed",
      "auto_speak",
      "notifications",
    ]) {
      if ((args as any)[k] !== undefined) patch[k] = (args as any)[k];
    }
    await ctx.db.patch(p._id, patch);
    return { ok: true };
  },
});