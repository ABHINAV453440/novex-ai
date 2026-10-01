import { query, mutation } from "./_generated/server";
import { v } from "convex/values";
import { Id } from "./_generated/dataModel";

export const getByUsername = query({
  args: { username: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db.query("users")
      .withIndex("by_username", (q) => q.eq("username", args.username.toLowerCase()))
      .first();
  },
});

export const getByEmail = query({
  args: { email: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db.query("users")
      .withIndex("by_email", (q) => q.eq("email", args.email.toLowerCase()))
      .first();
  },
});

export const getById = query({
  args: { id: v.string() },
  handler: async (ctx, args) => {
    try {
      return await ctx.db.get(args.id as Id<"users">);
    } catch {
      return null;
    }
  },
});

export const create = mutation({
  args: {
    username: v.string(),
    email: v.string(),
    password_hash: v.optional(v.string()),
    display_name: v.string(),
    email_verified: v.boolean(),
    auth_provider: v.string(),
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    return await ctx.db.insert("users", {
      username: args.username.toLowerCase(),
      email: args.email.toLowerCase(),
      password_hash: args.password_hash,
      display_name: args.display_name,
      email_verified: args.email_verified,
      auth_provider: args.auth_provider,
      created: now,
      updated: now,
    });
  },
});

export const updateLastLogin = mutation({
  args: { id: v.string() },
  handler: async (ctx, args) => {
    await ctx.db.patch(args.id as Id<"users">, {
      last_login: Date.now(),
      updated: Date.now(),
    });
    return { ok: true };
  },
});

export const updatePassword = mutation({
  args: { id: v.string(), password_hash: v.string() },
  handler: async (ctx, args) => {
    await ctx.db.patch(args.id as Id<"users">, {
      password_hash: args.password_hash,
      updated: Date.now(),
    });
    return { ok: true };
  },
});

export const set2FA = mutation({
  args: {
    id: v.string(),
    secret: v.union(v.string(), v.null()),
    enabled: v.boolean(),
  },
  handler: async (ctx, args) => {
    await ctx.db.patch(args.id as Id<"users">, {
      totp_secret: args.secret || undefined,
      totp_enabled: args.enabled,
      updated: Date.now(),
    });
    return { ok: true };
  },
});

export const deleteUser = mutation({
  args: { id: v.string() },
  handler: async (ctx, args) => {
    const uid = args.id;
    // Delete related data (best-effort)
    const tables = [
      "chats", "docs", "flashcards", "memory", "personas",
      "projects", "reminders", "settings", "user_progress",
      "user_badges", "usage", "login_history",
    ];
    for (const t of tables) {
      try {
        const items = await (ctx.db.query as any)(t)
          .withIndex("by_user", (q: any) => q.eq("user_id", uid))
          .collect();
        for (const it of items) await ctx.db.delete(it._id);
      } catch {
        // Table might not have by_user index
      }
    }
    await ctx.db.delete(args.id as Id<"users">);
    return { ok: true };
  },
});

export const search = query({
  args: { q: v.string(), me_id: v.optional(v.union(v.string(), v.null())) },
  handler: async (ctx, args) => {
    const q = args.q.toLowerCase();
    const all = await ctx.db.query("users").collect();
    const out: any[] = [];
    for (const u of all) {
      if (args.me_id && u._id === args.me_id) continue;
      if (
        u.username.toLowerCase().includes(q) ||
        (u.display_name || "").toLowerCase().includes(q)
      ) {
        out.push({ username: u.username, display_name: u.display_name });
        if (out.length >= 10) break;
      }
    }
    return out;
  },
});