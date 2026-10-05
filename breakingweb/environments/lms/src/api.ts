import type { ApiRequestOptions } from "@breakingweb/shared";

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

type RequestFn = <T>(path: string, options?: ApiRequestOptions) => Promise<T>;

export function createLmsApi(request: RequestFn) {
  return {
    /* Profile */
    getProfile: () =>
      request<{ student: Student }>("profile").then((r) => r.student),
    updateProfile: (body: { name?: string; email?: string }) =>
      request<{ student: Student }>("profile/update", { method: "POST", body }).then((r) => r.student),

    /* Courses */
    listCourses: () =>
      request<{ items: Course[] }>("courses").then((r) => r.items),
    getCourse: (courseId: string) =>
      request<{ course: Course }>(`courses/${courseId}`).then((r) => r.course),
    getSyllabus: (courseId: string) =>
      request<{ course_id: string; course_code: string; title: string; syllabus: Course["syllabus"] }>(
        `courses/${courseId}/syllabus`,
      ),
    dropCourse: (courseId: string) =>
      request<{ enrollment: Enrollment; dropped: boolean }>(`courses/${courseId}/drop`, { method: "POST" }),

    /* Enrollments */
    listEnrollments: () =>
      request<{ items: Enrollment[] }>("enrollments").then((r) => r.items),
    createEnrollment: (courseId: string, role?: "student" | "ta") =>
      request<{ enrollment: Enrollment }>("enrollments", {
        method: "POST",
        body: { course_id: courseId, role: role ?? "student" },
      }).then((r) => r.enrollment),

    /* Assignments */
    listAssignments: (courseId: string) =>
      request<{ items: Assignment[] }>(`courses/${courseId}/assignments`).then((r) => r.items),
    getAssignment: (assignmentId: string) =>
      request<{ assignment: Assignment }>(`assignments/${assignmentId}`).then((r) => r.assignment),
    getRubric: (assignmentId: string) =>
      request<{ assignment_id: string; rubric: Assignment["rubric"] }>(`assignments/${assignmentId}/rubric`),
    submitAssignment: (assignmentId: string, fileName: string) =>
      request<{ assignment: Assignment }>(`assignments/${assignmentId}/submit`, {
        method: "POST",
        body: { file_name: fileName },
      }).then((r) => r.assignment),
    resubmitAssignment: (assignmentId: string, fileName: string) =>
      request<{ assignment: Assignment }>(`assignments/${assignmentId}/resubmit`, {
        method: "POST",
        body: { file_name: fileName },
      }).then((r) => r.assignment),

    /* Modules */
    listModules: (courseId: string) =>
      request<{ items: Module[] }>(`courses/${courseId}/modules`).then((r) => r.items),
    getModule: (moduleId: string) =>
      request<{ module: Module }>(`modules/${moduleId}`).then((r) => r.module),
    completeModuleItem: (moduleId: string, itemIndex: number) =>
      request<{ module: Module; modules?: Module[] }>(`modules/${moduleId}/items/${itemIndex}/complete`, { method: "POST" }).then(
        (r) => r,
      ),
    completeModule: (moduleId: string) =>
      request<{ module: Module; modules?: Module[] }>(`modules/${moduleId}/complete`, { method: "POST" }).then((r) => r),

    /* Discussions */
    listDiscussions: (courseId: string) =>
      request<{ items: Discussion[] }>(`courses/${courseId}/discussions`).then((r) => r.items),
    getDiscussion: (discussionId: string) =>
      request<{ discussion: Discussion; posts: DiscussionPost[] }>(`discussions/${discussionId}`),
    createPost: (discussionId: string, body: string) =>
      request<{ post: DiscussionPost }>(`discussions/${discussionId}/posts`, {
        method: "POST",
        body: { body },
      }).then((r) => r.post),
    replyToPost: (discussionId: string, postId: string, body: string) =>
      request<{ post: DiscussionPost }>(`discussions/${discussionId}/posts/${postId}/reply`, {
        method: "POST",
        body: { body },
      }).then((r) => r.post),
    updatePost: (discussionId: string, postId: string, body: string) =>
      request<{ post: DiscussionPost }>(`discussions/${discussionId}/posts/${postId}`, {
        method: "PUT",
        body: { body },
      }).then((r) => r.post),

    /* Peer Reviews */
    listPeerReviews: () =>
      request<{ items: PeerReview[] }>("peer-reviews").then((r) => r.items),
    getPeerReview: (reviewId: string) =>
      request<{ peer_review: PeerReview }>(`peer-reviews/${reviewId}`).then((r) => r.peer_review),
    submitPeerReview: (reviewId: string, rubricScores: Record<string, number>, comments: string) =>
      request<{ peer_review: PeerReview }>(`peer-reviews/${reviewId}/submit`, {
        method: "POST",
        body: { rubric_scores: rubricScores, comments },
      }).then((r) => r.peer_review),

    /* Grades */
    getCourseGrades: (courseId: string) =>
      request<{
        course_id: string;
        course_code: string;
        weighted_score: string | null;
        category_scores: Record<string, string | null>;
        grades: Grade[];
      }>(`courses/${courseId}/grades`),
    getAssignmentGrade: (assignmentId: string) =>
      request<{
        assignment_id: string;
        assignment_title: string;
        score: string | null;
        points_possible: string;
        feedback: string | null;
        submission_status: string;
        grade: Grade | null;
      }>(`grades/${assignmentId}`),
    whatIfGrades: (courseId: string, hypotheticalScores: Record<string, string>) =>
      request<{
        course_id: string;
        what_if_weighted_score: string | null;
        hypothetical_scores: Record<string, string>;
      }>(`courses/${courseId}/grades/what-if`, {
        method: "POST",
        body: { hypothetical_scores: hypotheticalScores },
      }),

    /* Announcements */
    listAnnouncements: (courseId?: string) =>
      request<{ items: Announcement[] }>("announcements", {
        query: courseId ? { course_id: courseId } : undefined,
      }).then((r) => r.items),
    markAnnouncementRead: (announcementId: string) =>
      request<{ announcement: Announcement }>(`announcements/${announcementId}/read`, { method: "POST" }).then(
        (r) => r.announcement,
      ),
    markAllAnnouncementsRead: () =>
      request<{ marked_read: number }>("announcements/mark_all_read", { method: "POST" }),

    /* Calendar */
    getCalendar: (courseId?: string) =>
      request<{ items: CalendarEvent[] }>("calendar", {
        query: courseId ? { course_id: courseId } : undefined,
      }).then((r) => r.items),

    /* Messages */
    listMessages: () =>
      request<{ items: SentMessage[] }>("messages").then((r) => r.items),
    sendMessage: (to: string, subject: string, body: string) =>
      request<{ message: SentMessage; sent: boolean }>("messages/send", {
        method: "POST",
        body: { to, subject, body },
      }),
  };
}
