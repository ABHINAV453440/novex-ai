import { v } from "convex/values";
import { query, mutation } from "./_generated/server";

// ============================================================
// 📅 STUDY PLANNER
// ============================================================
export const listPlans = query({
  args: { user_id: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("study_plans")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .order("desc")
      .collect();
  },
});

export const getPlan = query({
  args: { plan_id: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db.get(args.plan_id as any);
  },
});

export const createPlan = mutation({
  args: {
    user_id: v.string(),
    title: v.string(),
    exam_name: v.optional(v.string()),
    exam_date: v.optional(v.string()),
    days: v.number(),
    hours_per_day: v.number(),
    subjects: v.array(v.string()),
    plan_json: v.string(),
  },
  handler: async (ctx, args) => {
    const id = await ctx.db.insert("study_plans", {
      user_id: args.user_id,
      title: args.title,
      exam_name: args.exam_name || "",
      exam_date: args.exam_date || "",
      days: args.days,
      hours_per_day: args.hours_per_day,
      subjects: args.subjects,
      plan_json: args.plan_json,
      created: Date.now(),
      updated: Date.now(),
    });
    return { ok: true, id };
  },
});

export const updatePlanProgress = mutation({
  args: { plan_id: v.string(), task_index: v.number(), done: v.boolean() },
  handler: async (ctx, args) => {
    const plan = await ctx.db.get(args.plan_id as any);
    if (!plan) return { error: "Not found" };
    let planData: any = {};
    try { planData = JSON.parse(plan.plan_json); } catch { planData = { tasks: [] }; }
    if (!planData.completed) planData.completed = {};
    planData.completed[String(args.task_index)] = args.done;
    await ctx.db.patch(args.plan_id as any, {
      plan_json: JSON.stringify(planData),
      updated: Date.now(),
    });
    return { ok: true };
  },
});

export const deletePlan = mutation({
  args: { plan_id: v.string() },
  handler: async (ctx, args) => {
    await ctx.db.delete(args.plan_id as any);
    return { ok: true };
  },
});

// ============================================================
// 📊 PROGRESS TRACKER
// ============================================================
export const recordQuizAttempt = mutation({
  args: {
    user_id: v.string(),
    topic: v.string(),
    subject: v.string(),
    difficulty: v.string(),
    total: v.number(),
    score: v.number(),
    wrong_topics: v.array(v.string()),
    time_taken: v.number(),
    mode: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const id = await ctx.db.insert("quiz_attempts", {
      user_id: args.user_id,
      topic: args.topic,
      subject: args.subject,
      difficulty: args.difficulty,
      total: args.total,
      score: args.score,
      wrong_topics: args.wrong_topics,
      time_taken: args.time_taken,
      mode: args.mode || "mcq",
      created: Date.now(),
    });
    return { ok: true, id };
  },
});

export const listQuizAttempts = query({
  args: { user_id: v.string(), limit: v.optional(v.number()) },
  handler: async (ctx, args) => {
    const limit = args.limit || 100;
    const items = await ctx.db
      .query("quiz_attempts")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .order("desc")
      .take(limit);
    return items;
  },
});

export const getProgressStats = query({
  args: { user_id: v.string() },
  handler: async (ctx, args) => {
    const attempts = await ctx.db
      .query("quiz_attempts")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .collect();

    const totalAttempts = attempts.length;
    const totalQuestions = attempts.reduce((sum, a) => sum + (a.total || 0), 0);
    const totalCorrect = attempts.reduce((sum, a) => sum + (a.score || 0), 0);
    const avgScore = totalQuestions > 0 ? Math.round((totalCorrect / totalQuestions) * 100) : 0;

    const subjectStats: Record<string, { total: number; correct: number; attempts: number }> = {};
    const topicStats: Record<string, { total: number; correct: number; wrong: number }> = {};

    attempts.forEach((a) => {
      const subj = a.subject || "General";
      if (!subjectStats[subj]) subjectStats[subj] = { total: 0, correct: 0, attempts: 0 };
      subjectStats[subj].total += a.total || 0;
      subjectStats[subj].correct += a.score || 0;
      subjectStats[subj].attempts += 1;

      const top = a.topic || "General";
      if (!topicStats[top]) topicStats[top] = { total: 0, correct: 0, wrong: 0 };
      topicStats[top].total += a.total || 0;
      topicStats[top].correct += a.score || 0;
      topicStats[top].wrong += (a.total || 0) - (a.score || 0);
    });

    const subjectArr = Object.keys(subjectStats).map((k) => ({
      subject: k,
      total: subjectStats[k].total,
      correct: subjectStats[k].correct,
      attempts: subjectStats[k].attempts,
      pct: subjectStats[k].total > 0 ? Math.round((subjectStats[k].correct / subjectStats[k].total) * 100) : 0,
    }));

    const topicArr = Object.keys(topicStats).map((k) => ({
      topic: k,
      total: topicStats[k].total,
      correct: topicStats[k].correct,
      wrong: topicStats[k].wrong,
      pct: topicStats[k].total > 0 ? Math.round((topicStats[k].correct / topicStats[k].total) * 100) : 0,
    }));

    const weakTopics = topicArr.filter((t) => t.total >= 3 && t.pct < 60).sort((a, b) => a.pct - b.pct).slice(0, 5);
    const strongTopics = topicArr.filter((t) => t.total >= 3 && t.pct >= 80).sort((a, b) => b.pct - a.pct).slice(0, 5);

    const now = Date.now();
    const dayMs = 24 * 60 * 60 * 1000;
    const trend: any[] = [];
    for (let i = 29; i >= 0; i--) {
      const dayStart = now - i * dayMs - (now % dayMs);
      const dayEnd = dayStart + dayMs;
      const dayAttempts = attempts.filter((a) => a.created >= dayStart && a.created < dayEnd);
      const dayTotal = dayAttempts.reduce((s, a) => s + (a.total || 0), 0);
      const dayCorrect = dayAttempts.reduce((s, a) => s + (a.score || 0), 0);
      trend.push({
        date: new Date(dayStart).toISOString().slice(0, 10),
        attempts: dayAttempts.length,
        pct: dayTotal > 0 ? Math.round((dayCorrect / dayTotal) * 100) : 0,
      });
    }

    return {
      totalAttempts,
      totalQuestions,
      totalCorrect,
      avgScore,
      subjectStats: subjectArr,
      topicStats: topicArr,
      weakTopics,
      strongTopics,
      trend,
    };
  },
});

export const clearQuizAttempts = mutation({
  args: { user_id: v.string() },
  handler: async (ctx, args) => {
    const items = await ctx.db
      .query("quiz_attempts")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .collect();
    for (const it of items) await ctx.db.delete(it._id);
    return { ok: true, deleted: items.length };
  },
});

// ============================================================
// 🔥 STUDY STREAK
// ============================================================
export const recordActivity = mutation({
  args: {
    user_id: v.string(),
    activity_type: v.string(),
  },
  handler: async (ctx, args) => {
    const today = new Date().toISOString().slice(0, 10);
    const existing = await ctx.db
      .query("streaks")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .first();

    if (!existing) {
      const id = await ctx.db.insert("streaks", {
        user_id: args.user_id,
        current_streak: 1,
        longest_streak: 1,
        last_active_date: today,
        total_active_days: 1,
        activities: [{ date: today, type: args.activity_type }],
        created: Date.now(),
        updated: Date.now(),
      });
      return { ok: true, current_streak: 1, is_new: true };
    }

    if (existing.last_active_date === today) {
      const activities = (existing.activities || []).slice(-50);
      activities.push({ date: today, type: args.activity_type });
      await ctx.db.patch(existing._id, { activities, updated: Date.now() });
      return { ok: true, current_streak: existing.current_streak, is_new: false };
    }

    const yesterday = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
    let newStreak = 1;
    if (existing.last_active_date === yesterday) {
      newStreak = existing.current_streak + 1;
    }
    const longest = Math.max(existing.longest_streak || 1, newStreak);
    const activities = (existing.activities || []).slice(-50);
    activities.push({ date: today, type: args.activity_type });

    await ctx.db.patch(existing._id, {
      current_streak: newStreak,
      longest_streak: longest,
      last_active_date: today,
      total_active_days: (existing.total_active_days || 0) + 1,
      activities,
      updated: Date.now(),
    });
    return { ok: true, current_streak: newStreak, is_new: true };
  },
});

export const getStreak = query({
  args: { user_id: v.string() },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query("streaks")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .first();
    if (!existing) {
      return { current_streak: 0, longest_streak: 0, last_active_date: "", total_active_days: 0, activities: [] };
    }
    const yesterday = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
    const today = new Date().toISOString().slice(0, 10);
    const isActive = existing.last_active_date === today || existing.last_active_date === yesterday;
    return {
      current_streak: isActive ? existing.current_streak : 0,
      longest_streak: existing.longest_streak,
      last_active_date: existing.last_active_date,
      total_active_days: existing.total_active_days,
      activities: existing.activities || [],
    };
  },
});

// ============================================================
// ⏱️ POMODORO SESSIONS
// ============================================================
export const recordPomodoro = mutation({
  args: {
    user_id: v.string(),
    duration_min: v.number(),
    task: v.optional(v.string()),
    subject: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const today = new Date().toISOString().slice(0, 10);
    const id = await ctx.db.insert("pomodoro_sessions", {
      user_id: args.user_id,
      duration_min: args.duration_min,
      task: args.task || "",
      subject: args.subject || "",
      date: today,
      created: Date.now(),
    });
    return { ok: true, id };
  },
});

export const getPomodoroStats = query({
  args: { user_id: v.string() },
  handler: async (ctx, args) => {
    const today = new Date().toISOString().slice(0, 10);
    const weekAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
    const all = await ctx.db
      .query("pomodoro_sessions")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .collect();

    const todaySessions = all.filter((s) => s.date === today);
    const weekSessions = all.filter((s) => s.date >= weekAgo);
    return {
      today_count: todaySessions.length,
      today_minutes: todaySessions.reduce((s, x) => s + (x.duration_min || 0), 0),
      week_count: weekSessions.length,
      week_minutes: weekSessions.reduce((s, x) => s + (x.duration_min || 0), 0),
      total_count: all.length,
      total_minutes: all.reduce((s, x) => s + (x.duration_min || 0), 0),
    };
  },
});

// ============================================================
// 🏫 CLASSES (Teacher)
// ============================================================
export const createClass = mutation({
  args: {
    teacher_id: v.string(),
    name: v.string(),
    subject: v.string(),
    description: v.optional(v.string()),
    class_code: v.string(),
  },
  handler: async (ctx, args) => {
    const id = await ctx.db.insert("classes", {
      teacher_id: args.teacher_id,
      name: args.name,
      subject: args.subject,
      description: args.description || "",
      class_code: args.class_code,
      students: [],
      created: Date.now(),
      updated: Date.now(),
    });
    return { ok: true, id };
  },
});

export const listClassesByTeacher = query({
  args: { teacher_id: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("classes")
      .withIndex("by_teacher", (q) => q.eq("teacher_id", args.teacher_id))
      .order("desc")
      .collect();
  },
});

export const listClassesByStudent = query({
  args: { student_id: v.string() },
  handler: async (ctx, args) => {
    const all = await ctx.db.query("classes").collect();
    return all.filter((c) => (c.students || []).some((s: any) => s.user_id === args.student_id));
  },
});

export const getClassByCode = query({
  args: { class_code: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("classes")
      .withIndex("by_code", (q) => q.eq("class_code", args.class_code.toUpperCase()))
      .first();
  },
});

export const getClass = query({
  args: { class_id: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db.get(args.class_id as any);
  },
});

export const joinClass = mutation({
  args: {
    class_id: v.string(),
    user_id: v.string(),
    username: v.string(),
    display_name: v.string(),
  },
  handler: async (ctx, args) => {
    const cls = await ctx.db.get(args.class_id as any);
    if (!cls) return { error: "Class not found" };
    const students = cls.students || [];
    if (students.some((s: any) => s.user_id === args.user_id)) {
      return { ok: true, already_joined: true };
    }
    students.push({
      user_id: args.user_id,
      username: args.username,
      display_name: args.display_name,
      joined: Date.now(),
    });
    await ctx.db.patch(args.class_id as any, { students, updated: Date.now() });
    return { ok: true };
  },
});

export const removeStudent = mutation({
  args: { class_id: v.string(), user_id: v.string() },
  handler: async (ctx, args) => {
    const cls = await ctx.db.get(args.class_id as any);
    if (!cls) return { error: "Class not found" };
    const students = (cls.students || []).filter((s: any) => s.user_id !== args.user_id);
    await ctx.db.patch(args.class_id as any, { students, updated: Date.now() });
    return { ok: true };
  },
});

export const deleteClass = mutation({
  args: { class_id: v.string() },
  handler: async (ctx, args) => {
    await ctx.db.delete(args.class_id as any);
    return { ok: true };
  },
});

// ============================================================
// 📝 ASSIGNMENTS
// ============================================================
export const createAssignment = mutation({
  args: {
    class_id: v.string(),
    teacher_id: v.string(),
    title: v.string(),
    description: v.string(),
    questions_json: v.string(),
    due_date: v.string(),
    total_marks: v.number(),
  },
  handler: async (ctx, args) => {
    const id = await ctx.db.insert("assignments", {
      class_id: args.class_id,
      teacher_id: args.teacher_id,
      title: args.title,
      description: args.description,
      questions_json: args.questions_json,
      due_date: args.due_date,
      total_marks: args.total_marks,
      created: Date.now(),
      updated: Date.now(),
    });
    return { ok: true, id };
  },
});

export const listAssignmentsByClass = query({
  args: { class_id: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("assignments")
      .withIndex("by_class", (q) => q.eq("class_id", args.class_id))
      .order("desc")
      .collect();
  },
});

export const getAssignment = query({
  args: { assignment_id: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db.get(args.assignment_id as any);
  },
});

export const submitAssignment = mutation({
  args: {
    assignment_id: v.string(),
    student_id: v.string(),
    student_name: v.string(),
    answers_json: v.string(),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query("submissions")
      .withIndex("by_assignment", (q) => q.eq("assignment_id", args.assignment_id))
      .collect();
    const mine = existing.find((s: any) => s.student_id === args.student_id);
    if (mine) {
      await ctx.db.patch(mine._id, {
        answers_json: args.answers_json,
        submitted: Date.now(),
        status: "submitted",
      });
      return { ok: true, id: mine._id, resubmitted: true };
    }
    const id = await ctx.db.insert("submissions", {
      assignment_id: args.assignment_id,
      student_id: args.student_id,
      student_name: args.student_name,
      answers_json: args.answers_json,
      grade_json: "",
      status: "submitted",
      submitted: Date.now(),
      created: Date.now(),
    });
    return { ok: true, id };
  },
});

export const listSubmissions = query({
  args: { assignment_id: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("submissions")
      .withIndex("by_assignment", (q) => q.eq("assignment_id", args.assignment_id))
      .collect();
  },
});

export const listMySubmission = query({
  args: { assignment_id: v.string(), student_id: v.string() },
  handler: async (ctx, args) => {
    const all = await ctx.db
      .query("submissions")
      .withIndex("by_assignment", (q) => q.eq("assignment_id", args.assignment_id))
      .collect();
    return all.find((s: any) => s.student_id === args.student_id) || null;
  },
});

export const saveGrade = mutation({
  args: {
    submission_id: v.string(),
    grade_json: v.string(),
    score: v.number(),
  },
  handler: async (ctx, args) => {
    await ctx.db.patch(args.submission_id as any, {
      grade_json: args.grade_json,
      score: args.score,
      status: "graded",
      graded: Date.now(),
    });
    return { ok: true };
  },
});

export const deleteAssignment = mutation({
  args: { assignment_id: v.string() },
  handler: async (ctx, args) => {
    const subs = await ctx.db
      .query("submissions")
      .withIndex("by_assignment", (q) => q.eq("assignment_id", args.assignment_id))
      .collect();
    for (const s of subs) await ctx.db.delete(s._id);
    await ctx.db.delete(args.assignment_id as any);
    return { ok: true };
  },
});

// ============================================================
// 📚 QUESTION BANK
// ============================================================
export const saveQuestion = mutation({
  args: {
    user_id: v.string(),
    subject: v.string(),
    topic: v.string(),
    qtype: v.string(),
    difficulty: v.string(),
    question_json: v.string(),
    tags: v.array(v.string()),
  },
  handler: async (ctx, args) => {
    const id = await ctx.db.insert("question_bank", {
      user_id: args.user_id,
      subject: args.subject,
      topic: args.topic,
      qtype: args.qtype,
      difficulty: args.difficulty,
      question_json: args.question_json,
      tags: args.tags,
      created: Date.now(),
    });
    return { ok: true, id };
  },
});

export const listQuestions = query({
  args: {
    user_id: v.string(),
    subject: v.optional(v.string()),
    topic: v.optional(v.string()),
    qtype: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    let items = await ctx.db
      .query("question_bank")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .order("desc")
      .collect();
    if (args.subject) items = items.filter((q) => q.subject === args.subject);
    if (args.topic) items = items.filter((q) => q.topic === args.topic);
    if (args.qtype) items = items.filter((q) => q.qtype === args.qtype);
    return items;
  },
});

export const deleteQuestion = mutation({
  args: { question_id: v.string() },
  handler: async (ctx, args) => {
    await ctx.db.delete(args.question_id as any);
    return { ok: true };
  },
});

export const bulkSaveQuestions = mutation({
  args: {
    user_id: v.string(),
    subject: v.string(),
    topic: v.string(),
    qtype: v.string(),
    difficulty: v.string(),
    questions_json: v.array(v.string()),
  },
  handler: async (ctx, args) => {
    const ids: string[] = [];
    for (const qJson of args.questions_json) {
      const id = await ctx.db.insert("question_bank", {
        user_id: args.user_id,
        subject: args.subject,
        topic: args.topic,
        qtype: args.qtype,
        difficulty: args.difficulty,
        question_json: qJson,
        tags: [args.topic],
        created: Date.now(),
      });
      ids.push(id as any);
    }
    return { ok: true, count: ids.length };
  },
});

// ============================================================
// 💬 CLASS CHAT
// ============================================================
export const sendClassMessage = mutation({
  args: {
    class_id: v.string(),
    user_id: v.string(),
    username: v.string(),
    display_name: v.string(),
    role: v.string(),
    content: v.string(),
  },
  handler: async (ctx, args) => {
    const id = await ctx.db.insert("class_messages", {
      class_id: args.class_id,
      user_id: args.user_id,
      username: args.username,
      display_name: args.display_name,
      role: args.role,
      content: args.content.slice(0, 2000),
      created: Date.now(),
    });
    return { ok: true, id };
  },
});

export const listClassMessages = query({
  args: { class_id: v.string(), limit: v.optional(v.number()) },
  handler: async (ctx, args) => {
    const limit = args.limit || 100;
    const items = await ctx.db
      .query("class_messages")
      .withIndex("by_class", (q) => q.eq("class_id", args.class_id))
      .order("desc")
      .take(limit);
    return items.reverse();
  },
});

export const deleteClassMessage = mutation({
  args: { message_id: v.string() },
  handler: async (ctx, args) => {
    await ctx.db.delete(args.message_id as any);
    return { ok: true };
  },
});

// ============================================================
// 📅 ATTENDANCE
// ============================================================
export const markAttendance = mutation({
  args: {
    class_id: v.string(),
    teacher_id: v.string(),
    date: v.string(),
    records: v.array(v.object({
      user_id: v.string(),
      display_name: v.string(),
      present: v.boolean(),
    })),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query("attendance")
      .withIndex("by_class_date", (q) => q.eq("class_id", args.class_id).eq("date", args.date))
      .first();
    if (existing) {
      await ctx.db.patch(existing._id, {
        records: args.records,
        updated: Date.now(),
      });
      return { ok: true, id: existing._id, updated: true };
    }
    const id = await ctx.db.insert("attendance", {
      class_id: args.class_id,
      teacher_id: args.teacher_id,
      date: args.date,
      records: args.records,
      created: Date.now(),
      updated: Date.now(),
    });
    return { ok: true, id };
  },
});

export const getAttendanceByDate = query({
  args: { class_id: v.string(), date: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("attendance")
      .withIndex("by_class_date", (q) => q.eq("class_id", args.class_id).eq("date", args.date))
      .first();
  },
});

export const listAttendance = query({
  args: { class_id: v.string(), limit: v.optional(v.number()) },
  handler: async (ctx, args) => {
    const limit = args.limit || 60;
    return await ctx.db
      .query("attendance")
      .withIndex("by_class", (q) => q.eq("class_id", args.class_id))
      .order("desc")
      .take(limit);
  },
});

export const getStudentAttendanceStats = query({
  args: { class_id: v.string(), user_id: v.string() },
  handler: async (ctx, args) => {
    const all = await ctx.db
      .query("attendance")
      .withIndex("by_class", (q) => q.eq("class_id", args.class_id))
      .collect();
    let present = 0, total = 0;
    all.forEach((a) => {
      const rec = (a.records || []).find((r: any) => r.user_id === args.user_id);
      if (rec) {
        total++;
        if (rec.present) present++;
      }
    });
    return { present, total, pct: total > 0 ? Math.round((present / total) * 100) : 0 };
  },
});

// ============================================================
// 🏆 LEADERBOARD
// ============================================================
export const getClassLeaderboard = query({
  args: { class_id: v.string() },
  handler: async (ctx, args) => {
    const cls = await ctx.db.get(args.class_id as any);
    if (!cls) return { entries: [] };
    const students = cls.students || [];
    const entries: any[] = [];

    const allAttempts = await ctx.db.query("quiz_attempts").collect();
    const allPomodoros = await ctx.db.query("pomodoro_sessions").collect();
    const allStreaks = await ctx.db.query("streaks").collect();

    students.forEach((s: any) => {
      const myAttempts = allAttempts.filter((a: any) => a.user_id === s.user_id);
      const totalQ = myAttempts.reduce((sum: number, a: any) => sum + (a.total || 0), 0);
      const totalC = myAttempts.reduce((sum: number, a: any) => sum + (a.score || 0), 0);
      const avgPct = totalQ > 0 ? Math.round((totalC / totalQ) * 100) : 0;
      const quizCount = myAttempts.length;

      const myPomo = allPomodoros.filter((p: any) => p.user_id === s.user_id);
      const focusMinutes = myPomo.reduce((sum: number, p: any) => sum + (p.duration_min || 0), 0);

      const myStreak = allStreaks.find((x: any) => x.user_id === s.user_id);
      const streak = myStreak ? myStreak.current_streak || 0 : 0;

      const score = Math.round(
        avgPct * 0.4 +
        Math.min(quizCount * 2, 20) +
        Math.min(focusMinutes / 30, 20) +
        Math.min(streak * 2, 20)
      );

      entries.push({
        user_id: s.user_id,
        display_name: s.display_name,
        username: s.username,
        avg_pct: avgPct,
        quiz_count: quizCount,
        total_questions: totalQ,
        focus_minutes: focusMinutes,
        streak: streak,
        score: score,
      });
    });

    entries.sort((a, b) => b.score - a.score);
    entries.forEach((e, i) => { e.rank = i + 1; });
    return { entries };
  },
});

// ============================================================
// 📜 CERTIFICATES
// ============================================================
export const saveCertificate = mutation({
  args: {
    user_id: v.string(),
    title: v.string(),
    recipient_name: v.string(),
    achievement: v.string(),
    issued_by: v.string(),
    cert_json: v.string(),
  },
  handler: async (ctx, args) => {
    const id = await ctx.db.insert("certificates", {
      user_id: args.user_id,
      title: args.title,
      recipient_name: args.recipient_name,
      achievement: args.achievement,
      issued_by: args.issued_by,
      cert_json: args.cert_json,
      issued_at: Date.now(),
      created: Date.now(),
    });
    return { ok: true, id };
  },
});

export const listCertificates = query({
  args: { user_id: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("certificates")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .order("desc")
      .collect();
  },
});

export const deleteCertificate = mutation({
  args: { cert_id: v.string() },
  handler: async (ctx, args) => {
    await ctx.db.delete(args.cert_id as any);
    return { ok: true };
  },
});

// ============================================================
// 📚 STUDY MATERIALS
// ============================================================
export const addMaterial = mutation({
  args: {
    class_id: v.string(),
    teacher_id: v.string(),
    title: v.string(),
    description: v.string(),
    file_url: v.string(),
    file_name: v.string(),
    file_type: v.string(),
    file_size: v.number(),
  },
  handler: async (ctx, args) => {
    const id = await ctx.db.insert("study_materials", {
      class_id: args.class_id,
      teacher_id: args.teacher_id,
      title: args.title,
      description: args.description,
      file_url: args.file_url,
      file_name: args.file_name,
      file_type: args.file_type,
      file_size: args.file_size,
      created: Date.now(),
    });
    return { ok: true, id };
  },
});

export const listMaterials = query({
  args: { class_id: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("study_materials")
      .withIndex("by_class", (q) => q.eq("class_id", args.class_id))
      .order("desc")
      .collect();
  },
});

export const deleteMaterial = mutation({
  args: { material_id: v.string() },
  handler: async (ctx, args) => {
    await ctx.db.delete(args.material_id as any);
    return { ok: true };
  },
});

// ============================================================
// 📆 TIMETABLES
// ============================================================
export const saveTimetable = mutation({
  args: {
    user_id: v.string(),
    title: v.string(),
    scope: v.string(),
    class_id: v.optional(v.string()),
    timetable_json: v.string(),
  },
  handler: async (ctx, args) => {
    const id = await ctx.db.insert("timetables", {
      user_id: args.user_id,
      title: args.title,
      scope: args.scope,
      class_id: args.class_id || "",
      timetable_json: args.timetable_json,
      created: Date.now(),
      updated: Date.now(),
    });
    return { ok: true, id };
  },
});

export const listTimetables = query({
  args: { user_id: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("timetables")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .order("desc")
      .collect();
  },
});

export const listClassTimetables = query({
  args: { class_id: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("timetables")
      .withIndex("by_class", (q) => q.eq("class_id", args.class_id))
      .order("desc")
      .collect();
  },
});

export const deleteTimetable = mutation({
  args: { timetable_id: v.string() },
  handler: async (ctx, args) => {
    await ctx.db.delete(args.timetable_id as any);
    return { ok: true };
  },
});

// ============================================================
// 💬 DIRECT MESSAGES
// ============================================================
export const sendDM = mutation({
  args: {
    from_id: v.string(),
    from_name: v.string(),
    to_id: v.string(),
    to_name: v.string(),
    content: v.string(),
  },
  handler: async (ctx, args) => {
    const id = await ctx.db.insert("direct_messages", {
      from_id: args.from_id,
      from_name: args.from_name,
      to_id: args.to_id,
      to_name: args.to_name,
      content: args.content.slice(0, 2000),
      read: false,
      created: Date.now(),
    });
    return { ok: true, id };
  },
});

export const getConversation = query({
  args: { user_a: v.string(), user_b: v.string(), limit: v.optional(v.number()) },
  handler: async (ctx, args) => {
    const limit = args.limit || 200;
    const all = await ctx.db.query("direct_messages").collect();
    const mine = all.filter(
      (m) =>
        (m.from_id === args.user_a && m.to_id === args.user_b) ||
        (m.from_id === args.user_b && m.to_id === args.user_a)
    );
    mine.sort((a, b) => a.created - b.created);
    return mine.slice(-limit);
  },
});

export const listConversations = query({
  args: { user_id: v.string() },
  handler: async (ctx, args) => {
    const all = await ctx.db.query("direct_messages").collect();
    const mine = all.filter((m) => m.from_id === args.user_id || m.to_id === args.user_id);
    const convMap: Record<string, any> = {};
    mine.forEach((m) => {
      const other_id = m.from_id === args.user_id ? m.to_id : m.from_id;
      const other_name = m.from_id === args.user_id ? m.to_name : m.from_name;
      if (!convMap[other_id] || m.created > convMap[other_id].last_created) {
        convMap[other_id] = {
          other_id,
          other_name,
          last_message: m.content.slice(0, 80),
          last_created: m.created,
          unread_count: 0,
        };
      }
      if (m.to_id === args.user_id && !m.read) {
        if (!convMap[other_id].unread_count) convMap[other_id].unread_count = 0;
        convMap[other_id].unread_count += 1;
      }
    });
    const list = Object.values(convMap).sort((a, b) => b.last_created - a.last_created);
    return { conversations: list };
  },
});

export const markDMRead = mutation({
  args: { user_id: v.string(), other_id: v.string() },
  handler: async (ctx, args) => {
    const all = await ctx.db.query("direct_messages").collect();
    const unread = all.filter((m) => m.to_id === args.user_id && m.from_id === args.other_id && !m.read);
    for (const m of unread) await ctx.db.patch(m._id, { read: true });
    return { ok: true };
  },
});

// ============================================================
// 📚 VIDEO LESSONS
// ============================================================
export const addVideoLesson = mutation({
  args: {
    class_id: v.string(),
    teacher_id: v.string(),
    title: v.string(),
    description: v.string(),
    video_url: v.string(),
    duration_min: v.number(),
  },
  handler: async (ctx, args) => {
    const id = await ctx.db.insert("video_lessons", {
      class_id: args.class_id,
      teacher_id: args.teacher_id,
      title: args.title,
      description: args.description,
      video_url: args.video_url,
      duration_min: args.duration_min,
      created: Date.now(),
    });
    return { ok: true, id };
  },
});

export const listVideoLessons = query({
  args: { class_id: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("video_lessons")
      .withIndex("by_class", (q) => q.eq("class_id", args.class_id))
      .order("desc")
      .collect();
  },
});

export const deleteVideoLesson = mutation({
  args: { video_id: v.string() },
  handler: async (ctx, args) => {
    await ctx.db.delete(args.video_id as any);
    return { ok: true };
  },
});

// ============================================================
// 🎫 HALL TICKETS
// ============================================================
export const createHallTicket = mutation({
  args: {
    user_id: v.string(),
    exam_name: v.string(),
    exam_date: v.string(),
    exam_time: v.string(),
    duration_min: v.number(),
    center: v.string(),
    subjects: v.array(v.string()),
    roll_prefix: v.string(),
    instructions: v.string(),
  },
  handler: async (ctx, args) => {
    const id = await ctx.db.insert("hall_tickets", {
      user_id: args.user_id,
      exam_name: args.exam_name,
      exam_date: args.exam_date,
      exam_time: args.exam_time,
      duration_min: args.duration_min,
      center: args.center,
      subjects: args.subjects,
      roll_prefix: args.roll_prefix,
      instructions: args.instructions,
      created: Date.now(),
    });
    return { ok: true, id };
  },
});

export const listHallTickets = query({
  args: { user_id: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("hall_tickets")
      .withIndex("by_user", (q) => q.eq("user_id", args.user_id))
      .order("desc")
      .collect();
  },
});

export const deleteHallTicket = mutation({
  args: { ticket_id: v.string() },
  handler: async (ctx, args) => {
    await ctx.db.delete(args.ticket_id as any);
    return { ok: true };
  },
});

// ============================================================
// 📖 READING LIST
// ============================================================
export const addReading = mutation({
  args: {
    class_id: v.string(),
    teacher_id: v.string(),
    title: v.string(),
    author: v.string(),
    description: v.string(),
    link: v.string(),
    type: v.string(),
  },
  handler: async (ctx, args) => {
    const id = await ctx.db.insert("reading_list", {
      class_id: args.class_id,
      teacher_id: args.teacher_id,
      title: args.title,
      author: args.author,
      description: args.description,
      link: args.link,
      type: args.type,
      created: Date.now(),
    });
    return { ok: true, id };
  },
});

export const listReading = query({
  args: { class_id: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("reading_list")
      .withIndex("by_class", (q) => q.eq("class_id", args.class_id))
      .order("desc")
      .collect();
  },
});

export const deleteReading = mutation({
  args: { reading_id: v.string() },
  handler: async (ctx, args) => {
    await ctx.db.delete(args.reading_id as any);
    return { ok: true };
  },
});