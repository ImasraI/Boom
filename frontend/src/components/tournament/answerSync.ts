export type TournamentAnswers = Record<string, number | null>;
export type AnswerSaveState = "saved" | "pending" | "saving" | "error";

interface QueueOptions {
  revision: number;
  savedRevision: number;
  answers: TournamentAnswers;
  save: (answers: TournamentAnswers, revision: number, signal: AbortSignal) => Promise<{ revision: number }>;
  onState: (state: AnswerSaveState) => void;
  isActive: () => boolean;
}

/** One immutable write at a time. A late acknowledgement cannot erase a newer edit. */
export class TournamentAnswerQueue {
  revision: number;
  savedRevision: number;
  answers: TournamentAnswers;
  private pending: { answers: TournamentAnswers; revision: number } | null;
  private inFlight: Promise<void> | null = null;
  private controller: AbortController | null = null;
  private cancelled = false;
  constructor(private options: QueueOptions) {
    this.revision = options.revision;
    this.savedRevision = options.savedRevision;
    this.answers = { ...options.answers };
    this.pending = this.revision > this.savedRevision ? { answers: { ...this.answers }, revision: this.revision } : null;
  }
  get hasPending() { return this.revision > this.savedRevision; }
  stage(answers: TournamentAnswers) {
    if (this.cancelled || JSON.stringify(answers) === JSON.stringify(this.answers)) return;
    this.answers = { ...answers };
    this.revision += 1;
    this.pending = { answers: { ...answers }, revision: this.revision };
    this.options.onState("pending");
  }
  flush(): Promise<void> {
    if (this.cancelled || !this.options.isActive()) return Promise.reject(new Error("حساب یا بازی تغییر کرده است."));
    if (this.inFlight) return this.inFlight;
    const write = async () => {
      while (this.pending && !this.cancelled && this.options.isActive()) {
        const snapshot = this.pending;
        this.pending = null;
        const controller = new AbortController();
        this.controller = controller;
        this.options.onState("saving");
        try {
          const result = await this.options.save(snapshot.answers, snapshot.revision, controller.signal);
          if (this.cancelled || controller.signal.aborted || !this.options.isActive()) return;
          if (result.revision < snapshot.revision) throw new Error("نسخهٔ پاسخ‌ها تأیید نشد؛ دوباره ذخیره کن.");
          this.savedRevision = Math.max(this.savedRevision, result.revision);
          this.options.onState(this.pending ? "pending" : "saved");
        } catch (failure) {
          const newer = this.pending as { answers: TournamentAnswers; revision: number } | null;
          if (!newer || newer.revision < snapshot.revision) this.pending = snapshot;
          if (!this.cancelled && !controller.signal.aborted && this.options.isActive()) this.options.onState("error");
          throw failure;
        } finally { if (this.controller === controller) this.controller = null; }
      }
    };
    const promise = write();
    this.inFlight = promise;
    void promise.then(() => { if (this.inFlight === promise) this.inFlight = null; }, () => { if (this.inFlight === promise) this.inFlight = null; });
    return promise;
  }
  activate() { this.cancelled = false; }
  cancel() { this.cancelled = true; this.controller?.abort(); }
}
