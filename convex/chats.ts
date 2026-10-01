import { query, mutation } from "./_generated/server";
import { v } from "convex/values";
import { Id } from "./_generated/dataModel";

export const create = mutation({
  args: {
    user_id: v.string(),
    title: v.string(),
    project_id: v.optional(v.union(v.string(), v.null())),
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    return await ctx.db.insert("chats", {
      user_id: args.user_id,
      title: args.title.slice(0, 100),
      project_id: args.project_id || undefined,
      messages: [],
      collaborators: [],
      created: now,
      updated: now,
    });
  },
});

export const getById = query({
  args: {
    id: v.string(),
    viewer_id: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const chat = await ctx.db.get(args.id as Id<"chats">);
    if (!chat) return null;
    if (args.viewer_id && chat.user_id !== args.viewer_id) {
      const collabs = chat.collaborators || [];
      if (!collabs.includes(args.viewer_id)) return null;
    }
    return chat;
  },
});

export const listByUser = query({
  args: {
    user_id: v.string(),
    project_id: v.optional(v.union(v.string(), v.null())),
  },
  handler: async (ctx, args) => {
    const all = await ctx.db.query("chats")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .collect();
    let filtered = all;
    if (args.project_id !== undefined) {
      filtered = all.filter((c) => c.project_id === (args.project_id || undefined));
    }
    return filtered
      .sort((a, b) => b.updated - a.updated)
      .map((c) => ({
        id: c._id,
        title: c.title,
        updated: c.updated,
        project_id: c.project_id,
      }));
  },
});

export const appendMessage = mutation({
  args: {
    chat_id: v.string(),
    role: v.string(),
    content: v.string(),
    attachments: v.optional(v.array(v.string())),
    sender: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const chat = await ctx.db.get(args.chat_id as Id<"chats">);
    if (!chat) return { ok: false };
    const messages = [
      ...chat.messages,
      {
        role: args.role,
        content: args.content,
        attachments: args.attachments,
        sender: args.sender,
        created: Date.now(),
      },
    ];
    await ctx.db.patch(args.chat_id as Id<"chats">, {
      messages,
      updated: Date.now(),
    });
    return { ok: true };
  },
});

export const update = mutation({
  args: {
    chat_id: v.string(),
    title: v.optional(v.string()),
    project_id: v.optional(v.union(v.string(), v.null())),
  },
  handler: async (ctx, args) => {
    const patch: any = { updated: Date.now() };
    if (args.title !== undefined) patch.title = args.title;
    if (args.project_id !== undefined) patch.project_id = args.project_id || undefined;
    await ctx.db.patch(args.chat_id as Id<"chats">, patch);
    return { ok: true };
  },
});

export const remove = mutation({
  args: { id: v.string() },
  handler: async (ctx, args) => {
    await ctx.db.delete(args.id as Id<"chats">);
    return { ok: true };
  },
});

export const listCollaborators = query({
  args: { chat_id: v.string() },
  handler: async (ctx, args) => {
    const chat = await ctx.db.get(args.chat_id as Id<"chats">);
    if (!chat) return [];
    const out: any[] = [];
    for (const uid of chat.collaborators || []) {
      const u = await ctx.db.get(uid as Id<"users">);
      if (u) out.push({ username: u.username, display_name: u.display_name });
    }
    return out;
  },
});

export const addCollaborator = mutation({
  args: { chat_id: v.string(), username: v.string() },
  handler: async (ctx, args) => {
    const user = await ctx.db.query("users")
      .withIndex("by_username", (q) => q.eq("username", args.username.toLowerCase()))
      .first();
    if (!user) return { error: "User not found" };
    const chat = await ctx.db.get(args.chat_id as Id<"chats">);
    if (!chat) return { error: "Chat not found" };
    const collabs = [...(chat.collaborators || [])];
    if (!collabs.includes(user._id)) collabs.push(user._id);
    await ctx.db.patch(args.chat_id as Id<"chats">, {
      collaborators: collabs,
      updated: Date.now(),
    });
    return { ok: true };
  },
});

export const removeCollaborator = mutation({
  args: { chat_id: v.string(), username: v.string() },
  handler: async (ctx, args) => {
    const user = await ctx.db.query("users")
      .withIndex("by_username", (q) => q.eq("username", args.username.toLowerCase()))
      .first();
    if (!user) return { ok: false };
    const chat = await ctx.db.get(args.chat_id as Id<"chats">);
    if (!chat) return { ok: false };
    const collabs = (chat.collaborators || []).filter((u) => u !== user._id);
    await ctx.db.patch(args.chat_id as Id<"chats">, {
      collaborators: collabs,
      updated: Date.now(),
    });
    return { ok: true };
  },
});

export const getSharedWithUser = query({
  args: { user_id: v.string() },
  handler: async (ctx, args) => {
    const all = await ctx.db.query("chats").collect();
    const shared = all.filter((c) =>
      (c.collaborators || []).includes(args.user_id)
    );
    const out: any[] = [];
    for (const c of shared) {
      const owner = await ctx.db.get(c.user_id as Id<"users">);
      out.push({
        id: c._id,
        title: c.title,
        owner: owner?.username || "unknown",
        owner_display: owner?.display_name || "Unknown",
        updated: c.updated,
      });
    }
    return out;
  },
});