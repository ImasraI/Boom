import { apiJson } from "./api";
import type { QuestionFigureData } from "./questionFigures";

export type TournamentStage = "league" | "quarterfinal" | "semifinal" | "final" | "third_place";

export interface TournamentPlayer {
  id: number;
  name: string;
}

export interface TournamentStanding {
  rank: number;
  player_id: number;
  name: string;
  played: number;
  wins: number;
  draws: number;
  losses: number;
  points: number;
  buchholz: number;
  score_percent: number;
  tied: boolean;
}

export interface TournamentMatch {
  id: string;
  round_id: string;
  slot: number;
  stage: TournamentStage;
  player_a: TournamentPlayer | null;
  player_b: TournamentPlayer | null;
  score_a: number | null;
  score_b: number | null;
  winner_id: number | null;
  status: string;
  starts_at?: string;
  ends_at?: string;
}

export interface TournamentRound {
  id: string;
  number: number;
  stage: TournamentStage;
  label: string;
  starts_at: string | null;
  ends_at: string | null;
  status: string;
  matches: TournamentMatch[];
  question_count?: number;
}

export interface TournamentSummary {
  id: number;
  title: string;
  description: string;
  status: string;
  major: string;
  grade: string;
  capacity: number;
  league_rounds: number;
  playoff_size: number;
  duration_minutes: number;
  starts_at: string | null;
  registration_status: "closed";
  participant_count: number;
  attendance_grace_minutes?: number;
  ends_at?: string;
}

export interface TournamentDetail extends TournamentSummary {
  server_now?: string;
  tie_reason?: string | null;
  schedule_note?: string | null;
  standings: TournamentStanding[];
  rounds: TournamentRound[];
}

export interface TournamentPersonalMatch extends TournamentMatch {
  can_start: boolean;
  can_resume: boolean;
  has_submitted: boolean;
  reason: string | null;
  deadline_at: string | null;
}

export interface TournamentMe {
  player_id: number | null;
  matches: TournamentPersonalMatch[];
}

export interface TournamentQuestion {
  id: string;
  text: string;
  options: string[];
  subject: string;
  topic: string;
  figure?: QuestionFigureData | null;
}

export interface TournamentSession {
  match_id: string;
  tournament_id: number;
  title: string;
  questions: TournamentQuestion[];
  started_at: string;
  deadline_at: string;
  server_now: string;
  submitted: boolean;
  score: number | null;
  saved_answers?: Record<string, number | null>;
  answers_revision?: number;
}

export interface TournamentAnswerSave {
  revision: number;
  saved_at: string;
}

export interface TournamentSubmission {
  match_id: string;
  status: string;
  score: number | null;
  submitted: true;
}

// Aliases keep consumers readable without a second version of the wire model.
export type TournamentSubmitResult = TournamentSubmission;

const eventPath = (id: number) => `/api/tournaments/${id}`;
const matchPath = (id: number, matchId: string) => `${eventPath(id)}/matches/${encodeURIComponent(matchId)}`;

export function listTournaments(signal?: AbortSignal) {
  return apiJson<{ items: TournamentSummary[] }>("/api/tournaments", { signal });
}

export function getTournament(id: number, signal?: AbortSignal) {
  return apiJson<TournamentDetail>(eventPath(id), { signal });
}

export function getMyTournament(id: number, signal?: AbortSignal) {
  return apiJson<TournamentMe>(`${eventPath(id)}/me`, { signal });
}

export const getTournamentMe = getMyTournament;

export function startTournamentMatch(id: number, matchId: string, signal?: AbortSignal) {
  return apiJson<TournamentSession>(`${matchPath(id, matchId)}/start`, { method: "POST", signal });
}

export function submitTournamentMatch(id: number, matchId: string, answers: Record<string, number | null>, signal?: AbortSignal) {
  return apiJson<TournamentSubmission>(`${matchPath(id, matchId)}/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answers }),
    signal,
  });
}

export function saveTournamentAnswers(id: number, matchId: string, answers: Record<string, number | null>, revision: number, signal?: AbortSignal) {
  return apiJson<TournamentAnswerSave>(`${matchPath(id, matchId)}/answers`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answers, revision }),
    signal,
  });
}
