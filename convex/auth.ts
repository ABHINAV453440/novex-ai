import { query, mutation } from "./_generated/server";
import { v } from "convex/values";
import { Id } from "./_generated/dataModel";

export const recordLogin = mutation({
  args: {
    user_id: v.string(),
    ip: v.string(),
    ua: v.string(),
    success: v.boolean(),
  },
  handler: async (ctx, args) => {
    return await ctx.db.insert("login_history", {
      ...args,
      time: Date.now(),
    });
  },
});

export const getHistory = query({
  args: { user_id: v.string() },
  handler: async (ctx, args) => {
    const items = await ctx.db.query("login_history")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .collect();
    return items.sort((a, b) => b.time - a.time).slice(0, 20);
  },
});

export const clearHistory = mutation({
  args: { user_id: v.string() },
  handler: async (ctx, args) => {
    const items = await ctx.db.query("login_history")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .collect();
    for (const i of items) await ctx.db.delete(i._id);
    return { ok: true };
  },
});

export const createPending = mutation({
  args: {
    username: v.string(),
    email: v.string(),
    password_hash: v.string(),
    display_name: v.string(),
    code: v.string(),
  },
  handler: async (ctx, args) => {
    // Delete any existing pending for this username
    const existing = await ctx.db.query("pending_registrations")
      .withIndex("by_username", (q) => q.eq("username", args.username.toLowerCase()))
      .first();
    if (existing) await ctx.db.delete(existing._id);

    const expires = new Date(Date.now() + 15 * 60 * 1000).toISOString();
    return await ctx.db.insert("pending_registrations", {
      username: args.username.toLowerCase(),
      email: args.email.toLowerCase(),
      password_hash: args.password_hash,
      display_name: args.display_name,
      code: args.code,
      expires,
      created: Date.now(),
    });
  },
});

export const getPending = query({
  args: { username: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db.query("pending_registrations")
      .withIndex("by_username", (q) => q.eq("username", args.username.toLowerCase()))
      .first();
  },
});

export const updatePendingCode = mutation({
  args: { username: v.string(), code: v.string() },
  handler: async (ctx, args) => {
    const entry = await ctx.db.query("pending_registrations")
      .withIndex("by_username", (q) => q.eq("username", args.username.toLowerCase()))
      .first();
    if (!entry) return { ok: false };
    const expires = new Date(Date.now() + 15 * 60 * 1000).toISOString();
    await ctx.db.patch(entry._id, { code: args.code, expires });
    return { ok: true };
  },
});

export const deletePending = mutation({
  args: { username: v.string() },
  handler: async (ctx, args) => {
    const entry = await ctx.db.query("pending_registrations")
      .withIndex("by_username", (q) => q.eq("username", args.username.toLowerCase()))
      .first();
    if (entry) await ctx.db.delete(entry._id);
    return { ok: true };
  },
});

export const createReset = mutation({
  args: {
    token: v.string(),
    username: v.string(),
    email: v.string(),
    code: v.string(),
  },
  handler: async (ctx, args) => {
    const expires = new Date(Date.now() + 15 * 60 * 1000).toISOString();
    return await ctx.db.insert("password_resets", {
      token: args.token,
      username: args.username.toLowerCase(),
      email: args.email.toLowerCase(),
      code: args.code,
      expires,
      created: Date.now(),
    });
  },
});

export const findReset = query({
  args: { email: v.string(), code: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db.query("password_resets")
      .withIndex("by_email_code", (q) =>
        q.eq("email", args.email.toLowerCase()).eq("code", args.code)
      )
      .first();
  },
});

export const deleteReset = mutation({
  args: { token: v.string() },
  handler: async (ctx, args) => {
    const entry = await ctx.db.query("password_resets")
      .withIndex("by_token", (q) => q.eq("token", args.token))
      .first();
    if (entry) await ctx.db.delete(entry._id);
    return { ok: true };
  },
});