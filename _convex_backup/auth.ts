import { query, mutation } from "./_generated/server";
import { v } from "convex/values";

// ============ PENDING VERIFICATION ============
export const createPending = mutation({
  args: {
    username: v.string(),
    email: v.string(),
    password_hash: v.string(),
    display_name: v.string(),
    code: v.string(),
  },
  handler: async (ctx, args) => {
    const old = await ctx.db
      .query("pending_verify")
      .withIndex("by_username", (q) => q.eq("username", args.username))
      .collect();
    for (const o of old) await ctx.db.delete(o._id);

    const now = new Date();
    const expires = new Date(now.getTime() + 15 * 60 * 1000);

    await ctx.db.insert("pending_verify", {
      username: args.username.toLowerCase(),
      email: args.email.toLowerCase(),
      password_hash: args.password_hash,
      display_name: args.display_name,
      code: args.code,
      created: now.toISOString(),
      expires: expires.toISOString(),
    });
    return { ok: true };
  },
});

export const getPending = query({
  args: { username: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("pending_verify")
      .withIndex("by_username", (q) => q.eq("username", args.username.toLowerCase()))
      .first();
  },
});

export const updatePendingCode = mutation({
  args: { username: v.string(), code: v.string() },
  handler: async (ctx, args) => {
    const entry = await ctx.db
      .query("pending_verify")
      .withIndex("by_username", (q) => q.eq("username", args.username.toLowerCase()))
      .first();
    if (!entry) return { ok: false };
    const expires = new Date(Date.now() + 15 * 60 * 1000);
    await ctx.db.patch(entry._id, {
      code: args.code,
      expires: expires.toISOString(),
    });
    return { ok: true };
  },
});

export const deletePending = mutation({
  args: { username: v.string() },
  handler: async (ctx, args) => {
    const entries = await ctx.db
      .query("pending_verify")
      .withIndex("by_username", (q) => q.eq("username", args.username.toLowerCase()))
      .collect();
    for (const e of entries) await ctx.db.delete(e._id);
    return { ok: true };
  },
});

// ============ PASSWORD RESET ============
export const createReset = mutation({
  args: {
    token: v.string(),
    username: v.string(),
    email: v.string(),
    code: v.string(),
  },
  handler: async (ctx, args) => {
    const expires = new Date(Date.now() + 15 * 60 * 1000);
    await ctx.db.insert("reset_tokens", {
      token: args.token,
      username: args.username.toLowerCase(),
      email: args.email.toLowerCase(),
      code: args.code,
      expires: expires.toISOString(),
      attempts: 0,
    });
    return { ok: true };
  },
});

export const findReset = query({
  args: { email: v.string(), code: v.string() },
  handler: async (ctx, args) => {
    const entries = await ctx.db
      .query("reset_tokens")
      .withIndex("by_email", (q) => q.eq("email", args.email.toLowerCase()))
      .collect();
    const now = new Date();
    for (const e of entries) {
      if (e.code !== args.code) continue;
      if (new Date(e.expires) < now) continue;
      return e;
    }
    return null;
  },
});

export const deleteReset = mutation({
  args: { token: v.string() },
  handler: async (ctx, args) => {
    const entries = await ctx.db
      .query("reset_tokens")
      .withIndex("by_token", (q) => q.eq("token", args.token))
      .collect();
    for (const e of entries) await ctx.db.delete(e._id);
    return { ok: true };
  },
});

// ============ LOGIN HISTORY ============
export const recordLogin = mutation({
  args: {
    user_id: v.id("users"),
    ip: v.string(),
    ua: v.string(),
    success: v.boolean(),
  },
  handler: async (ctx, args) => {
    await ctx.db.insert("login_history", {
      user_id: args.user_id,
      time: new Date().toISOString(),
      ip: args.ip,
      ua: args.ua.slice(0, 200),
      success: args.success,
    });

    const all = await ctx.db
      .query("login_history")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .collect();
    if (all.length > 20) {
      const sorted = all.sort((a, b) => b.time.localeCompare(a.time));
      for (let i = 20; i < sorted.length; i++) {
        await ctx.db.delete(sorted[i]._id);
      }
    }
    return { ok: true };
  },
});

export const getHistory = query({
  args: { user_id: v.id("users") },
  handler: async (ctx, args) => {
    const all = await ctx.db
      .query("login_history")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .collect();
    return all.sort((a, b) => b.time.localeCompare(a.time)).slice(0, 20);
  },
});

export const clearHistory = mutation({
  args: { user_id: v.id("users") },
  handler: async (ctx, args) => {
    const all = await ctx.db
      .query("login_history")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .collect();
    for (const h of all) await ctx.db.delete(h._id);
    return { ok: true };
  },
});