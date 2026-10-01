import { v } from "convex/values";
import { query, mutation } from "./_generated/server";

export const getProgress = query({
  args: { user_id: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("user_progress")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .first();
  },
});

export const createProgress = mutation({
  args: { user_id: v.string() },
  handler: async (ctx, args) => {
    const now = Date.now();
    return await ctx.db.insert("user_progress", {
      user_id: args.user_id, exp: 0, level: "Beginner",
      level_icon: "🌱", quiz_count: 0, perfect_quizzes: 0,
      flashcards_reviewed: 0, docs_generated: 0, pomodoros_done: 0,
      doubts_solved: 0, memory_count: 0,
      created: now, updated: now,
    });
  },
});

export const updateProgress = mutation({
  args: {
    user_id: v.string(), exp: v.number(),
    level: v.string(), level_icon: v.string(),
  },
  handler: async (ctx, args) => {
    const p = await ctx.db
      .query("user_progress")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .first();
    if (!p) return { ok: false };
    await ctx.db.patch(p._id, {
      exp: args.exp, level: args.level,
      level_icon: args.level_icon, updated: Date.now(),
    });
    return { ok: true };
  },
});

export const incrementCounter = mutation({
  args: {
    user_id: v.string(), field: v.string(), amount: v.number(),
  },
  handler: async (ctx, args) => {
    const p = await ctx.db
      .query("user_progress")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .first();
    if (!p) return { ok: false };
    const allowed = ["quiz_count", "perfect_quizzes", "flashcards_reviewed",
      "docs_generated", "pomodoros_done", "doubts_solved", "memory_count"];
    if (!allowed.includes(args.field)) return { ok: false };
    const cur = (p as any)[args.field] || 0;
    await ctx.db.patch(p._id, {
      [args.field]: cur + args.amount, updated: Date.now(),
    });
    return { ok: true };
  },
});

export const resetProgress = mutation({
  args: { user_id: v.string() },
  handler: async (ctx, args) => {
    const p = await ctx.db
      .query("user_progress")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .first();
    if (p) {
      await ctx.db.patch(p._id, {
        exp: 0, level: "Beginner", level_icon: "🌱",
        quiz_count: 0, perfect_quizzes: 0, flashcards_reviewed: 0,
        docs_generated: 0, pomodoros_done: 0, doubts_solved: 0,
        memory_count: 0, updated: Date.now(),
      });
    }
    const badges = await ctx.db
      .query("user_badges")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .collect();
    for (const b of badges) await ctx.db.delete(b._id);
    return { ok: true };
  },
});

export const listBadges = query({
  args: { user_id: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("user_badges")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .collect();
  },
});

export const unlockBadge = mutation({
  args: {
    user_id: v.string(), badge_id: v.string(),
    badge_icon: v.string(), badge_name: v.string(),
    badge_desc: v.string(),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query("user_badges")
      .withIndex("by_user_badge", (q) =>
        q.eq("user_id", args.user_id).eq("badge_id", args.badge_id))
      .first();
    if (existing) return { ok: false, already: true };
    const id = await ctx.db.insert("user_badges", {
      user_id: args.user_id, badge_id: args.badge_id,
      badge_icon: args.badge_icon, badge_name: args.badge_name,
      badge_desc: args.badge_desc, unlocked_at: Date.now(),
    });
    return { ok: true, id };
  },
});

export const logExp = mutation({
  args: {
    user_id: v.string(), action: v.string(),
    exp_gained: v.number(), meta: v.string(),
  },
  handler: async (ctx, args) => {
    return await ctx.db.insert("exp_log", {
      user_id: args.user_id, action: args.action,
      exp_gained: args.exp_gained, meta: args.meta,
      created: Date.now(),
    });
  },
});