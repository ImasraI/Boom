import assessmentQuestions from "./assessmentQuestions.json";

export interface Question {
  id?: number;
  question: string;
  options: [string, string, string, string];
  answer: number;
}

export interface SubjectTest {
  mock_id?: number;
  id: string;
  name: string;
  icon: string;
  color: string;
  questions: Question[];
}

export const SUBJECT_TESTS = assessmentQuestions as unknown as SubjectTest[];
