import { query, mutation } from "./_generated/server";
import { v } from "convex/values";

export const getByUsername = query({
  args: { username: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("users")
      .withIndex("by_username", (q) => q.eq("username", args.username))
      .first();
  },
});

export const getByEmail = query({
  args: { email: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("users")
      .withIndex("by_email", (q) => q.eq("email", args.email.toLowerCase()))
      .first();
  },
});

export const getByGoogleId = query({
  args: { google_id: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("users")
      .withIndex("by_google_id", (q) => q.eq("google_id", args.google_id))
      .first();
  },
});

export const getById = query({
  args: { id: v.id("users") },
  handler: async (ctx, args) => {
    return await ctx.db.get(args.id);
  },
});

export const checkUsernameAvailable = query({
  args: { username: v.string() },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query("users")
      .withIndex("by_username", (q) => q.eq("username", args.username.toLowerCase()))
      .first();
    return { available: !existing };
  },
});

export const search = query({
  args: { q: v.string(), me_id: v.optional(v.id("users")) },
  handler: async (ctx, args) => {
    const all = await ctx.db.query("users").collect();
    const q = args.q.toLowerCase();
    return all
      .filter((u) => {
        if (args.me_id && u._id === args.me_id) return false;
        return u.username.toLowerCase().includes(q) || (u.display_name || "").toLowerCase().includes(q);
      })
      .slice(0, 10)
      .map((u) => ({ username: u.username, display_name: u.display_name }));
  },
});

export const create = mutation({
  args: {
    username: v.string(),
    email: v.string(),
    password_hash: v.string(),
    display_name: v.string(),
    email_verified: v.boolean(),
    google_id: v.optional(v.string()),
    auth_provider: v.string(),
  },
  handler: async (ctx, args) => {
    const now = new Date().toISOString();
    return await ctx.db.insert("users", {
      username: args.username.toLowerCase(),
      email: args.email.toLowerCase(),
      password_hash: args.password_hash,
      display_name: args.display_name,
      email_verified: args.email_verified,
      totp_secret: undefined,
      totp_enabled: false,
      google_id: args.google_id,
      auth_provider: args.auth_provider,
      created: now,
      last_login: now,
      login_count: 1,
    });
  },
});

export const updateLastLogin = mutation({
  args: { id: v.id("users") },
  handler: async (ctx, args) => {
    const user = await ctx.db.get(args.id);
    if (!user) return;
    await ctx.db.patch(args.id, {
      last_login: new Date().toISOString(),
      login_count: user.login_count + 1,
    });
  },
});

export const updatePassword = mutation({
  args: { id: v.id("users"), password_hash: v.string() },
  handler: async (ctx, args) => {
    await ctx.db.patch(args.id, { password_hash: args.password_hash });
  },
});

export const set2FA = mutation({
  args: {
    id: v.id("users"),
    secret: v.optional(v.string()),
    enabled: v.boolean(),
  },
  handler: async (ctx, args) => {
    await ctx.db.patch(args.id, {
      totp_secret: args.secret,
      totp_enabled: args.enabled,
    });
  },
});

export const linkGoogle = mutation({
  args: { id: v.id("users"), google_id: v.string() },
  handler: async (ctx, args) => {
    await ctx.db.patch(args.id, { google_id: args.google_id });
  },
});

export const deleteUser = mutation({
  args: { id: v.id("users") },
  handler: async (ctx, args) => {
    const tables = ["chats", "projects", "memory", "personas", "flashcards", "docs", "settings", "reminders", "stats", "login_history"] as const;
    for (const table of tables) {
      const items = await ctx.db.query(table).withIndex("by_user", (q: any) => q.eq("user_id", args.id)).collect();
      for (const item of items) await ctx.db.delete(item._id);
    }
    await ctx.db.delete(args.id);
    return { ok: true };
  },
});