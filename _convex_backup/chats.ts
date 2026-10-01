import { query, mutation } from "./_generated/server";
import { v } from "convex/values";

export const listByUser = query({
  args: {
    user_id: v.id("users"),
    project_id: v.optional(v.union(v.id("projects"), v.null())),
  },
  handler: async (ctx, args) => {
    let chats = await ctx.db
      .query("chats")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .collect();

    if (args.project_id !== undefined) {
      if (args.project_id === null) {
        chats = chats.filter((c) => !c.project_id);
      } else {
        chats = chats.filter((c) => c.project_id === args.project_id);
      }
    }

    return chats
      .sort((a, b) => b.updated.localeCompare(a.updated))
      .map((c) => ({
        id: c._id,
        title: c.title,
        updated: c.updated,
        count: c.messages.length,
        project_id: c.project_id,
      }));
  },
});

export const getById = query({
  args: { id: v.id("chats"), viewer_id: v.optional(v.id("users")) },
  handler: async (ctx, args) => {
    const chat = await ctx.db.get(args.id);
    if (!chat) return null;
    if (args.viewer_id) {
      const isOwner = chat.user_id === args.viewer_id;
      const isShared = (chat.shared_with || []).includes(args.viewer_id);
      if (!isOwner && !isShared) return null;
    }
    return chat;
  },
});

export const getSharedWithUser = query({
  args: { user_id: v.id("users") },
  handler: async (ctx, args) => {
    const allChats = await ctx.db.query("chats").collect();
    const shared = allChats.filter((c) =>
      (c.shared_with || []).includes(args.user_id)
    );
    const out = [];
    for (const c of shared) {
      const owner = await ctx.db.get(c.user_id);
      out.push({
        id: c._id,
        title: c.title,
        updated: c.updated,
        count: c.messages.length,
        owner_username: owner?.username || "unknown",
        owner_display: owner?.display_name || "Unknown",
      });
    }
    return out.sort((a, b) => b.updated.localeCompare(a.updated));
  },
});

export const create = mutation({
  args: {
    user_id: v.id("users"),
    title: v.string(),
    project_id: v.optional(v.id("projects")),
  },
  handler: async (ctx, args) => {
    const now = new Date().toISOString();
    return await ctx.db.insert("chats", {
      user_id: args.user_id,
      title: args.title.slice(0, 60),
      project_id: args.project_id,
      created: now,
      updated: now,
      messages: [],
      shared_with: [],
    });
  },
});

export const appendMessage = mutation({
  args: {
    chat_id: v.id("chats"),
    role: v.string(),
    content: v.string(),
    attachments: v.optional(v.array(v.string())),
    sender: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const chat = await ctx.db.get(args.chat_id);
    if (!chat) return { ok: false };
    const now = new Date().toISOString();
    const newMsg = {
      role: args.role,
      content: args.content,
      time: now,
      attachments: args.attachments,
      sender: args.sender,
    };
    await ctx.db.patch(args.chat_id, {
      messages: [...chat.messages, newMsg],
      updated: now,
    });
    return { ok: true };
  },
});

export const update = mutation({
  args: {
    chat_id: v.id("chats"),
    title: v.optional(v.string()),
    project_id: v.optional(v.union(v.id("projects"), v.null())),
  },
  handler: async (ctx, args) => {
    const patch: any = { updated: new Date().toISOString() };
    if (args.title !== undefined) patch.title = args.title.slice(0, 60);
    if (args.project_id !== undefined) {
      patch.project_id = args.project_id === null ? undefined : args.project_id;
    }
    await ctx.db.patch(args.chat_id, patch);
    return { ok: true };
  },
});

export const remove = mutation({
  args: { id: v.id("chats") },
  handler: async (ctx, args) => {
    await ctx.db.delete(args.id);
    return { ok: true };
  },
});

export const addCollaborator = mutation({
  args: { chat_id: v.id("chats"), username: v.string() },
  handler: async (ctx, args) => {
    const chat = await ctx.db.get(args.chat_id);
    if (!chat) return { error: "Chat not found" };
    const user = await ctx.db
      .query("users")
      .withIndex("by_username", (q) => q.eq("username", args.username.toLowerCase()))
      .first();
    if (!user) return { error: "User not found" };
    const shared = chat.shared_with || [];
    if (!shared.includes(user._id)) {
      await ctx.db.patch(args.chat_id, { shared_with: [...shared, user._id] });
    }
    return { ok: true };
  },
});

export const removeCollaborator = mutation({
  args: { chat_id: v.id("chats"), username: v.string() },
  handler: async (ctx, args) => {
    const chat = await ctx.db.get(args.chat_id);
    if (!chat) return { error: "Chat not found" };
    const user = await ctx.db
      .query("users")
      .withIndex("by_username", (q) => q.eq("username", args.username.toLowerCase()))
      .first();
    if (!user) return { error: "User not found" };
    const shared = (chat.shared_with || []).filter((id) => id !== user._id);
    await ctx.db.patch(args.chat_id, { shared_with: shared });
    return { ok: true };
  },
});

export const listCollaborators = query({
  args: { chat_id: v.id("chats") },
  handler: async (ctx, args) => {
    const chat = await ctx.db.get(args.chat_id);
    if (!chat) return [];
    const out = [];
    for (const uid of chat.shared_with || []) {
      const u = await ctx.db.get(uid);
      if (u) out.push({ username: u.username, display_name: u.display_name });
    }
    return out;
  },
});