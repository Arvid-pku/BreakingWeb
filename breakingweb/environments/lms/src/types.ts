/* TypeScript interfaces mirroring Pydantic models from backend/models/lms.py */

export interface Student {
  id: string;
  name: string;
  email: string;
  student_id: string;
  enrollment_status: "active" | "probation" | "suspended";
  gpa: string; // Decimal as string
  advisor_id: string;
  advisor_name: string;
}

export interface CategoryPolicy {
  weight: string; // Decimal as string
  drop_lowest: number;
}

export interface LatePolicy {
  penalty_per_day: string;
  max_late_days: number;
  grace_period_hours: number;
}

export interface Syllabus {
  grading_policy: Record<string, CategoryPolicy>;
  late_policy: LatePolicy;
}

export interface Course {
  id: string;
  course_code: string;
  title: string;
  instructor_id: string;
  instructor_name: string;
  semester: string;
  credits: number;
  syllabus: Syllabus;
  drop_deadline: string;
  final_exam_date: string;
}

export interface Enrollment {
  id: string;
  student_id: string;
  course_id: string;
  role: "student" | "ta";
  status: "enrolled" | "waitlisted" | "dropped" | "completed";
  final_grade: string | null;
  final_score: string | null;
}

export interface RubricItem {
  criterion: string;
  max_points: string;
  description: string;
}

export interface Assignment {
  id: string;
  course_id: string;
  title: string;
  type: "homework" | "essay" | "project" | "quiz" | "exam" | "peer_review" | "participation";
  due_at: string;
  points_possible: string;
  submission_status: "not_submitted" | "submitted" | "late" | "graded" | "resubmit_requested";
  score: string | null;
  feedback: string | null;
  attempt_count: number;
  max_attempts: number;
  rubric: RubricItem[];
  weight_category: string;
  submitted_at: string | null;
  file_name: string | null;
}

export interface ContentItem {
  title: string;
  type: "reading" | "video" | "quiz" | "assignment" | "external_link";
  completed: boolean;
  linked_assignment_id: string | null;
}

export interface Module {
  id: string;
  course_id: string;
  title: string;
  position: number;
  unlock_condition: "none" | "date" | "prerequisite" | "min_score";
  unlock_value: string[];
  unlock_logic: "all" | "any";
  status: "locked" | "available" | "completed";
  content_items: ContentItem[];
}

export interface Discussion {
  id: string;
  course_id: string;
  module_id: string | null;
  title: string;
  prompt: string;
  due_at: string;
  min_posts: number;
  min_replies: number;
  points_possible: string;
  weight_category: string;
}

export interface DiscussionPost {
  id: string;
  discussion_id: string;
  author_id: string;
  author_name: string;
  body: string;
  parent_post_id: string | null;
  timestamp: string;
  updated_at: string | null;
  is_anonymous: boolean;
}

export interface PeerReview {
  id: string;
  assignment_id: string;
  reviewer_student_id: string;
  reviewee_student_id: string;
  reviewee_name: string;
  submission_title: string;
  submission_body: string;
  assignment_rubric: RubricItem[];
  rubric_scores: Record<string, number>;
  comments: string;
  status: "assigned" | "in_progress" | "submitted";
  returned_for_revision: boolean;
  previous_rubric_scores: Record<string, number>;
  previous_comments: string;
  due_at: string;
}

export interface Announcement {
  id: string;
  course_id: string;
  title: string;
  body: string;
  posted_at: string;
  is_read: boolean;
  priority: "normal" | "urgent";
}

export interface Grade {
  id: string;
  enrollment_id: string;
  course_id: string;
  assignment_id: string;
  score: string | null;
  points_possible: string;
  weight_category: string;
  is_dropped: boolean;
  late_penalty_applied: string;
}

export interface SentMessage {
  to: string;
  subject: string;
  body: string;
  sent_at: string;
  from: string;
}

export interface CalendarEvent {
  id: string;
  course_id: string;
  title: string;
  event_type: "lecture" | "office_hours" | "exam" | "deadline" | "lab";
  start_datetime: string;
  end_datetime: string;
  location: string;
  recurrence: "none" | "weekly";
  recurrence_end_date: string | null;
}
