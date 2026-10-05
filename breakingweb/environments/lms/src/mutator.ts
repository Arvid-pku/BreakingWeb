import type { RouteMutator } from "@breakingweb/shared";

import type {
  Announcement,
  Assignment,
  CalendarEvent,
  Course,
  Discussion,
  DiscussionPost,
  Enrollment,
  Grade,
  Module,
  PeerReview,
  SentMessage,
  Student,
} from "./types";

/* ------------------------------------------------------------------ */
/*  LmsFixture -- matches the JSON fixture shape                      */
/* ------------------------------------------------------------------ */

export interface LmsFixture {
  env_id: string;
  task_id: string;
  student: Student;
  courses: Course[];
  enrollments: Enrollment[];
  assignments: Assignment[];
  modules: Module[];
  discussions: Discussion[];
  discussion_posts: DiscussionPost[];
  peer_reviews: PeerReview[];
  announcements: Announcement[];
  grades: Grade[];
  calendar_events: CalendarEvent[];
  sent_messages: SentMessage[];
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                           */
/* ------------------------------------------------------------------ */

let _idCounter = 0;
function genId(prefix: string): string {
  return `${prefix}_${Date.now()}_${++_idCounter}`;
}

/* ------------------------------------------------------------------ */
/*  Route matching                                                    */
/* ------------------------------------------------------------------ */

type Handler = (
  state: LmsFixture,
  params: Record<string, string>,
  body: Record<string, unknown> | undefined,
  query: Record<string, unknown> | undefined,
) => { state: LmsFixture; response: unknown };

interface Route {
  method: string;
  pattern: RegExp;
  paramNames: string[];
  handler: Handler;
}

const routes: Route[] = [];

function route(method: string, pattern: string, handler: Handler) {
  const paramNames: string[] = [];
  const regexStr = pattern.replace(/:(\w+)/g, (_, name) => {
    paramNames.push(name);
    return "([^/]+)";
  });
  routes.push({
    method: method.toUpperCase(),
    pattern: new RegExp(`^${regexStr}$`),
    paramNames,
    handler,
  });
}

function matchRoute(
  method: string,
  path: string,
): { handler: Handler; params: Record<string, string> } | null {
  const upper = method.toUpperCase();
  for (const r of routes) {
    if (r.method !== upper) continue;
    const m = path.match(r.pattern);
    if (m) {
      const params: Record<string, string> = {};
      r.paramNames.forEach((name, i) => { params[name] = m[i + 1]; });
      return { handler: r.handler, params };
    }
  }
  return null;
}

/* ------------------------------------------------------------------ */
/*  Profile                                                           */
/* ------------------------------------------------------------------ */

route("GET", "profile", (state) => ({
  state,
  response: { student: state.student },
}));

route("POST", "profile/update", (state, _params, body) => {
  if (body?.name) state.student.name = String(body.name);
  if (body?.email) state.student.email = String(body.email);
  return { state, response: { student: state.student } };
});

/* ------------------------------------------------------------------ */
/*  Courses                                                           */
/* ------------------------------------------------------------------ */

route("GET", "courses", (state) => {
  const enrolledIds = new Set(
    state.enrollments
      .filter((e) => e.student_id === state.student.id && e.status === "enrolled")
      .map((e) => e.course_id),
  );
  const items = state.courses.filter((c) => enrolledIds.has(c.id));
  return { state, response: { items } };
});

route("GET", "courses/:course_id", (state, params) => {
  const course = state.courses.find((c) => c.id === params.course_id);
  if (!course) return { state, response: { error: "Not found", status: 404 } };
  return { state, response: { course } };
});

route("GET", "courses/:course_id/syllabus", (state, params) => {
  const course = state.courses.find((c) => c.id === params.course_id);
  if (!course) return { state, response: { error: "Not found", status: 404 } };
  return { state, response: { course_id: params.course_id, course_code: course.course_code, title: course.title, syllabus: course.syllabus } };
});

route("POST", "courses/:course_id/drop", (state, params) => {
  const enrollment = state.enrollments.find(
    (e) => e.course_id === params.course_id && e.student_id === state.student.id,
  );
  if (!enrollment) return { state, response: { error: "Not found", status: 404 } };
  enrollment.status = "dropped";
  return { state, response: { enrollment, dropped: true } };
});

/* ------------------------------------------------------------------ */
/*  Enrollments                                                       */
/* ------------------------------------------------------------------ */

route("GET", "enrollments", (state) => {
  const items = state.enrollments.filter((e) => e.student_id === state.student.id);
  return { state, response: { items } };
});

route("POST", "enrollments", (state, _params, body) => {
  const enrollment: Enrollment = {
    id: genId("enrollment"),
    student_id: state.student.id,
    course_id: String(body?.course_id ?? ""),
    role: (body?.role as "student" | "ta") ?? "student",
    status: "enrolled",
    final_grade: null,
    final_score: null,
  };
  state.enrollments.push(enrollment);
  return { state, response: { enrollment } };
});

/* ------------------------------------------------------------------ */
/*  Assignments                                                       */
/* ------------------------------------------------------------------ */

route("GET", "courses/:course_id/assignments", (state, params) => {
  const items = state.assignments.filter((a) => a.course_id === params.course_id);
  return { state, response: { items } };
});

route("GET", "assignments/:assignment_id", (state, params) => {
  const assignment = state.assignments.find((a) => a.id === params.assignment_id);
  if (!assignment) return { state, response: { error: "Not found", status: 404 } };
  return { state, response: { assignment } };
});

route("GET", "assignments/:assignment_id/rubric", (state, params) => {
  const assignment = state.assignments.find((a) => a.id === params.assignment_id);
  if (!assignment) return { state, response: { error: "Not found", status: 404 } };
  return { state, response: { assignment_id: params.assignment_id, rubric: assignment.rubric } };
});

route("POST", "assignments/:assignment_id/submit", (state, params, body) => {
  const assignment = state.assignments.find((a) => a.id === params.assignment_id);
  if (!assignment) return { state, response: { error: "Not found", status: 404 } };
  assignment.submission_status = "submitted";
  assignment.attempt_count += 1;
  assignment.file_name = String(body?.file_name ?? "submission.pdf");
  assignment.submitted_at = new Date().toISOString();
  return { state, response: { assignment } };
});

route("POST", "assignments/:assignment_id/resubmit", (state, params, body) => {
  const assignment = state.assignments.find((a) => a.id === params.assignment_id);
  if (!assignment) return { state, response: { error: "Not found", status: 404 } };
  assignment.submission_status = "submitted";
  assignment.attempt_count += 1;
  assignment.file_name = String(body?.file_name ?? "submission_v2.pdf");
  assignment.submitted_at = new Date().toISOString();
  return { state, response: { assignment } };
});

/* ------------------------------------------------------------------ */
/*  Modules                                                           */
/* ------------------------------------------------------------------ */

route("GET", "courses/:course_id/modules", (state, params) => {
  const items = state.modules
    .filter((m) => m.course_id === params.course_id)
    .sort((a, b) => a.position - b.position);
  return { state, response: { items } };
});

route("GET", "modules/:module_id", (state, params) => {
  const mod = state.modules.find((m) => m.id === params.module_id);
  if (!mod) return { state, response: { error: "Not found", status: 404 } };
  return { state, response: { module: mod } };
});

route("POST", "modules/:module_id/items/:item_index/complete", (state, params) => {
  const mod = state.modules.find((m) => m.id === params.module_id);
  if (!mod) return { state, response: { error: "Not found", status: 404 } };
  const idx = parseInt(params.item_index, 10);
  if (idx >= 0 && idx < mod.content_items.length) {
    mod.content_items[idx].completed = true;
  }
  return { state, response: { module: mod } };
});

route("POST", "modules/:module_id/complete", (state, params) => {
  const mod = state.modules.find((m) => m.id === params.module_id);
  if (!mod) return { state, response: { error: "Not found", status: 404 } };
  mod.status = "completed";
  return { state, response: { module: mod } };
});

/* ------------------------------------------------------------------ */
/*  Discussions                                                       */
/* ------------------------------------------------------------------ */

route("GET", "courses/:course_id/discussions", (state, params) => {
  const items = state.discussions.filter((d) => d.course_id === params.course_id);
  return { state, response: { items } };
});

route("GET", "discussions/:discussion_id", (state, params) => {
  const discussion = state.discussions.find((d) => d.id === params.discussion_id);
  if (!discussion) return { state, response: { error: "Not found", status: 404 } };
  const posts = state.discussion_posts
    .filter((p) => p.discussion_id === params.discussion_id)
    .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
  return { state, response: { discussion, posts } };
});

route("POST", "discussions/:discussion_id/posts", (state, params, body) => {
  const post: DiscussionPost = {
    id: genId("post"),
    discussion_id: params.discussion_id,
    author_id: state.student.id,
    author_name: state.student.name,
    body: String(body?.body ?? ""),
    parent_post_id: null,
    timestamp: new Date().toISOString(),
    updated_at: null,
    is_anonymous: false,
  };
  state.discussion_posts.push(post);
  return { state, response: { post } };
});

route("GET", "discussions/:discussion_id/posts", (state, params) => {
  const posts = state.discussion_posts
    .filter((p) => p.discussion_id === params.discussion_id)
    .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
  return { state, response: { items: posts } };
});

route("POST", "discussions/:discussion_id/posts/:post_id/reply", (state, params, body) => {
  const post: DiscussionPost = {
    id: genId("post"),
    discussion_id: params.discussion_id,
    author_id: state.student.id,
    author_name: state.student.name,
    body: String(body?.body ?? ""),
    parent_post_id: params.post_id,
    timestamp: new Date().toISOString(),
    updated_at: null,
    is_anonymous: false,
  };
  state.discussion_posts.push(post);
  return { state, response: { post } };
});

route("PUT", "discussions/:discussion_id/posts/:post_id", (state, params, body) => {
  const post = state.discussion_posts.find(
    (p) => p.id === params.post_id && p.discussion_id === params.discussion_id,
  );
  if (!post) return { state, response: { error: "Not found", status: 404 } };
  post.body = String(body?.body ?? post.body);
  post.updated_at = new Date().toISOString();
  return { state, response: { post } };
});

/* ------------------------------------------------------------------ */
/*  Peer Reviews                                                      */
/* ------------------------------------------------------------------ */

route("GET", "peer-reviews", (state) => {
  const items = state.peer_reviews.filter((r) => r.reviewer_student_id === state.student.id);
  return { state, response: { items } };
});

route("GET", "peer-reviews/:review_id", (state, params) => {
  const review = state.peer_reviews.find((r) => r.id === params.review_id);
  if (!review) return { state, response: { error: "Not found", status: 404 } };
  return { state, response: { peer_review: review } };
});

route("POST", "peer-reviews/:review_id/submit", (state, params, body) => {
  const review = state.peer_reviews.find((r) => r.id === params.review_id);
  if (!review) return { state, response: { error: "Not found", status: 404 } };
  const rawScores = (body?.rubric_scores as Record<string, number>) ?? {};
  const normalisedScores: Record<string, number> = {};
  for (const [key, value] of Object.entries(rawScores)) {
    const parsed = Number.parseInt(String(value), 10);
    if (!Number.isNaN(parsed)) {
      normalisedScores[key.trim().toLowerCase().replace(/\s+/g, "_")] = Math.max(1, Math.min(5, parsed));
    }
  }
  review.returned_for_revision = false;
  review.status = "submitted";
  review.rubric_scores = normalisedScores;
  review.comments = String(body?.comments ?? "");
  return { state, response: { peer_review: review } };
});

/* ------------------------------------------------------------------ */
/*  Grades                                                            */
/* ------------------------------------------------------------------ */

route("GET", "courses/:course_id/grades", (state, params) => {
  const course = state.courses.find((c) => c.id === params.course_id);
  if (!course) return { state, response: { error: "Not found", status: 404 } };
  const grades = state.grades.filter((g) => g.course_id === params.course_id);

  // Compute category scores
  const categoryScores: Record<string, string | null> = {};
  for (const catName of Object.keys(course.syllabus.grading_policy)) {
    const catGrades = grades.filter((g) => g.weight_category === catName && g.score !== null);
    if (catGrades.length === 0) {
      categoryScores[catName] = null;
      continue;
    }
    // Find dropped grades
    const policy = course.syllabus.grading_policy[catName];
    const dropCount = Math.min(policy.drop_lowest, Math.max(0, catGrades.length - 1));
    const sorted = [...catGrades].sort((a, b) => {
      const ra = parseFloat(a.score!) / parseFloat(a.points_possible);
      const rb = parseFloat(b.score!) / parseFloat(b.points_possible);
      return ra - rb;
    });
    const droppedIds = new Set(sorted.slice(0, dropCount).map((g) => g.id));
    const active = catGrades.filter((g) => !droppedIds.has(g.id));
    if (active.length === 0) {
      categoryScores[catName] = null;
      continue;
    }
    let total = 0;
    for (const g of active) {
      const effective = parseFloat(g.score!) * (1 - parseFloat(g.late_penalty_applied));
      total += (effective / parseFloat(g.points_possible)) * 100;
    }
    categoryScores[catName] = (total / active.length).toFixed(2);
  }

  // Compute weighted score
  let gradedWeight = 0;
  let weightedSum = 0;
  for (const [catName, policy] of Object.entries(course.syllabus.grading_policy)) {
    const cs = categoryScores[catName];
    if (cs !== null) {
      const w = parseFloat(policy.weight);
      gradedWeight += w;
      weightedSum += parseFloat(cs) * w;
    }
  }
  const weightedScore = gradedWeight > 0 ? (weightedSum / gradedWeight).toFixed(2) : null;

  return {
    state,
    response: {
      course_id: params.course_id,
      course_code: course.course_code,
      weighted_score: weightedScore,
      category_scores: categoryScores,
      grades,
    },
  };
});

route("GET", "grades/:assignment_id", (state, params) => {
  const assignment = state.assignments.find((a) => a.id === params.assignment_id);
  if (!assignment) return { state, response: { error: "Not found", status: 404 } };
  const grade = state.grades.find((g) => g.assignment_id === params.assignment_id) ?? null;
  return {
    state,
    response: {
      assignment_id: params.assignment_id,
      assignment_title: assignment.title,
      score: assignment.score,
      points_possible: assignment.points_possible,
      feedback: assignment.feedback,
      submission_status: assignment.submission_status,
      grade,
    },
  };
});

route("POST", "courses/:course_id/grades/what-if", (state, params, body) => {
  const hypotheticalScores = (body?.hypothetical_scores as Record<string, string>) ?? {};
  const course = state.courses.find((c) => c.id === params.course_id);
  if (!course) {
    return { state, response: { error: "Not found", status: 404 } };
  }

  const assignmentToGradeScore = new Map<string, string>();
  const originalAssignmentStates = new Map<string, { score: string | null; submission_status: Assignment["submission_status"] }>();
  const originalGradeStates = new Map<string, { score: string | null; is_dropped: boolean; late_penalty_applied: string }>();
  const tempGradeIds = new Set<string>();
  const enrollment = state.enrollments.find(
    (enrollment) => enrollment.course_id === params.course_id && enrollment.student_id === state.student.id,
  );
  const courseAssignments = state.assignments.filter((a) => a.course_id === params.course_id);
  for (const [assignId, score] of Object.entries(hypotheticalScores)) {
    const assignment = courseAssignments.find((a) => a.id === assignId);
    if (assignment) {
      const scoreText = String(score);
      if (Number.isNaN(Number(scoreText))) {
        continue;
      }
      originalAssignmentStates.set(assignId, {
        score: assignment.score,
        submission_status: assignment.submission_status,
      });
      assignmentToGradeScore.set(assignId, scoreText);
      assignment.score = String(score);
      if (assignment.submission_status === "not_submitted") {
        assignment.submission_status = "submitted";
      }
    }
  }

  for (const grade of state.grades) {
    if (grade.course_id !== params.course_id) continue;
    if (!assignmentToGradeScore.has(grade.assignment_id)) {
      continue;
    }
    originalGradeStates.set(grade.id, {
      score: grade.score,
      is_dropped: grade.is_dropped,
      late_penalty_applied: grade.late_penalty_applied,
    });
    const nextScore = assignmentToGradeScore.get(grade.assignment_id);
    if (nextScore !== undefined) {
      grade.score = String(nextScore);
    }
  }

  // Create synthetic grade records for hypothetical-scored assignments that are
  // missing from the gradebook so what-if can include unsubmitted work.
  for (const assignment of courseAssignments) {
    const assignmentId = assignment.id;
    if (!assignmentToGradeScore.has(assignmentId)) continue;
    if (state.grades.some((g) => g.assignment_id === assignmentId)) continue;
    if (!enrollment) continue;

    let syntheticGradeId = `tmp_what_if_${assignmentId}`;
    while (state.grades.some((g) => g.id === syntheticGradeId)) {
      syntheticGradeId = `${syntheticGradeId}_x`;
    }
    state.grades.push({
      id: syntheticGradeId,
      enrollment_id: enrollment.id,
      course_id: params.course_id,
      assignment_id: assignmentId,
      score: assignment.score,
      points_possible: assignment.points_possible,
      weight_category: assignment.weight_category,
      is_dropped: false,
      late_penalty_applied: "0",
    });
    tempGradeIds.add(syntheticGradeId);
  }

  let weighted = 0;
  let weightedSum = 0;
  const policyEntries = Object.entries(course.syllabus.grading_policy);

  for (const [catName, catPolicy] of policyEntries) {
    const categoryGrades = state.grades.filter(
      (g) => g.course_id === params.course_id && g.weight_category === catName && g.score !== null,
    );
    if (categoryGrades.length === 0) continue;

    const dropCount = Math.min(catPolicy.drop_lowest, Math.max(0, categoryGrades.length - 1));
    const sorted = [...categoryGrades].sort((a, b) => {
      const ra = parseFloat(a.score!) / parseFloat(a.points_possible);
      const rb = parseFloat(b.score!) / parseFloat(b.points_possible);
      return ra - rb;
    });
    const droppedIds = new Set(sorted.slice(0, dropCount).map((g) => g.id));
    const active = categoryGrades.filter((g) => !droppedIds.has(g.id));
    if (active.length === 0) continue;

    let categoryTotal = 0;
    for (const g of active) {
      const effective = parseFloat(g.score!) * (1 - parseFloat(g.late_penalty_applied));
      categoryTotal += (effective / parseFloat(g.points_possible)) * 100;
    }

    const avg = categoryTotal / active.length;
    weightedSum += avg * parseFloat(catPolicy.weight);
    weighted += parseFloat(catPolicy.weight);
  }

  const whatIfWeighted = weighted > 0 ? (weightedSum / weighted).toFixed(2) : null;

  // Restore original grade states.
  for (const [assignmentId, assignmentState] of originalAssignmentStates) {
    const assignment = courseAssignments.find((a) => a.id === assignmentId);
    if (!assignment) continue;
    assignment.score = assignmentState.score;
    assignment.submission_status = assignmentState.submission_status;
  }
  for (const grade of state.grades) {
    if (grade.course_id !== params.course_id) continue;
    const original = originalGradeStates.get(grade.id);
    if (original !== undefined) {
      grade.score = original.score;
      grade.is_dropped = original.is_dropped;
      grade.late_penalty_applied = original.late_penalty_applied;
    }
  }
  if (tempGradeIds.size > 0) {
    state.grades = state.grades.filter((g) => !tempGradeIds.has(g.id));
  }

  return {
    state,
    response: {
      course_id: params.course_id,
      what_if_weighted_score: whatIfWeighted,
      hypothetical_scores: hypotheticalScores,
    },
  };
});

/* ------------------------------------------------------------------ */
/*  Announcements                                                     */
/* ------------------------------------------------------------------ */

route("GET", "announcements", (state, _params, _body, query) => {
  let items = [...state.announcements];
  if (query?.course_id) {
    items = items.filter((a) => a.course_id === String(query.course_id));
  }
  items.sort((a, b) => new Date(b.posted_at).getTime() - new Date(a.posted_at).getTime());
  return { state, response: { items } };
});

route("POST", "announcements/:announcement_id/read", (state, params) => {
  const ann = state.announcements.find((a) => a.id === params.announcement_id);
  if (!ann) return { state, response: { error: "Not found", status: 404 } };
  ann.is_read = true;
  return { state, response: { announcement: ann } };
});

route("POST", "announcements/mark_all_read", (state) => {
  let count = 0;
  for (const a of state.announcements) {
    if (!a.is_read) { a.is_read = true; count++; }
  }
  return { state, response: { marked_read: count } };
});

/* ------------------------------------------------------------------ */
/*  Calendar                                                          */
/* ------------------------------------------------------------------ */

route("GET", "calendar", (state, _params, _body, query) => {
  let items = [...state.calendar_events];
  if (query?.course_id) {
    items = items.filter((e) => e.course_id === String(query.course_id));
  }
  return { state, response: { items } };
});

/* ------------------------------------------------------------------ */
/*  Messages                                                          */
/* ------------------------------------------------------------------ */

route("GET", "messages", (state) => {
  return {
    state,
    response: {
      items: [...state.sent_messages].sort(
        (a, b) => new Date(b.sent_at).getTime() - new Date(a.sent_at).getTime(),
      ),
    },
  };
});

route("POST", "messages/send", (state, _params, body) => {
  const message = {
    to: String(body?.to ?? ""),
    subject: String(body?.subject ?? ""),
    body: String(body?.body ?? ""),
    sent_at: new Date().toISOString(),
    from: state.student.email,
  };
  state.sent_messages.push(message);
  return { state, response: { message, sent: true } };
});

/* ------------------------------------------------------------------ */
/*  Exported mutator                                                  */
/* ------------------------------------------------------------------ */

export const lmsMutator: RouteMutator<LmsFixture> = (
  state,
  method,
  path,
  body,
  query,
) => {
  const cleanPath = path.replace(/^\//, "");
  const match = matchRoute(method, cleanPath);
  if (!match) {
    return { state, response: { error: `No route: ${method} /${cleanPath}`, status: 404 } };
  }
  return match.handler(
    state,
    match.params,
    body as Record<string, unknown> | undefined,
    query,
  );
};
