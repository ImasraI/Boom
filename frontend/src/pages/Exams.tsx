import { useState } from "react";
import { NavFn } from "../types";

function BackButton({ onClick }: { onClick: () => void }) {
  return (
    <button onClick={onClick} className="w-9 h-9 rounded-xl bg-[#F0EBE3] flex items-center justify-center text-[var(--muted)] hover:bg-[#E5DDD4] transition-colors">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ transform: "scaleX(-1)" }}>
        <path d="M19 12H5M12 5l-7 7 7 7"/>
      </svg>
    </button>
  );
}

const EXAM_RESULTS = [
  {
    id: 1, provider: "قلم‌چی", date: "۲۵ مرداد ۱۴۰۵", totalScore: 68.4, rank: 4820,
    subjects: [
      { name: "حسابان", score: 82, correct: 41, wrong: 4, blank: 5 },
      { name: "فیزیک", score: 61, correct: 28, wrong: 9, blank: 13 },
      { name: "شیمی", score: 74, correct: 35, wrong: 6, blank: 9 },
      { name: "ادبیات", score: 71, correct: 33, wrong: 7, blank: 10 },
      { name: "عربی", score: 55, correct: 24, wrong: 12, blank: 14 },
    ],
  },
  {
    id: 2, provider: "گاج", date: "۱۱ مرداد ۱۴۰۵", totalScore: 64.1, rank: 6200,
    subjects: [
      { name: "حسابان", score: 78, correct: 39, wrong: 6, blank: 5 },
      { name: "فیزیک", score: 58, correct: 26, wrong: 11, blank: 13 },
      { name: "شیمی", score: 69, correct: 32, wrong: 9, blank: 9 },
      { name: "ادبیات", score: 65, correct: 31, wrong: 8, blank: 11 },
      { name: "عربی", score: 51, correct: 22, wrong: 14, blank: 14 },
    ],
  },
];

function ScoreBar({ score }: { score: number }) {
  const color = score >= 80 ? "#6B9E7A" : score >= 60 ? "#C4714A" : "#C44A4A";
  return (
    <div className="flex items-center gap-2">
      <span className="text-[12px] font-bold w-8 text-left" style={{ color }}>{score}%</span>
      <div className="flex-1 h-1.5 bg-[#F0EBE3] rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${score}%`, background: color }} />
      </div>
    </div>
  );
}

export default function Exams({ nav }: { nav: NavFn }) {
  const [selected, setSelected] = useState<number | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadDone, setUploadDone] = useState(false);

  const exam = EXAM_RESULTS.find(e => e.id === selected);

  function handleUpload() {
    setUploading(true);
    setTimeout(() => { setUploading(false); setUploadDone(true); setTimeout(() => setUploadDone(false), 2000); }, 1500);
  }

  return (
    <div className="min-h-screen bg-[#F8F6F2] pb-10">
      <div className="px-5 pt-12 pb-4 flex items-center gap-4">
        <BackButton onClick={() => selected ? setSelected(null) : nav("home")} />
        <div className="text-right">
          <h1 className="font-display text-xl text-[var(--text)]">
            {selected ? exam?.provider : "آزمون‌ها"}
          </h1>
          <p className="text-[12px] text-[var(--muted-2)] font-medium">
            {selected ? exam?.date : "نتایج و تحلیل عملکرد"}
          </p>
        </div>
      </div>

      {!selected ? (
        <div className="px-5 space-y-4">
          {/* Upload */}
          <button onClick={handleUpload}
            className="w-full bg-[var(--card)] rounded-2xl border-2 border-dashed border-[#E5DDD4] hover:border-[#C4714A] p-5 flex items-center gap-4 transition-all active:scale-[0.98] group">
            <div className="w-11 h-11 rounded-xl bg-[#FFF5F0] group-hover:bg-[#FFE8DC] flex items-center justify-center transition-colors flex-shrink-0">
              {uploading ? (
                <div className="w-5 h-5 border-2 border-[#C4714A] border-t-transparent rounded-full animate-spin" />
              ) : uploadDone ? (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#6B9E7A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
              ) : (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#C4714A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
                </svg>
              )}
            </div>
            <div className="text-right flex-1">
              <p className="text-[14px] font-bold text-[var(--text)]">
                {uploadDone ? "آپلود شد! در حال تحلیل..." : "آپلود نتایج آزمون"}
              </p>
              <p className="text-[12px] text-[var(--muted-2)] font-medium mt-0.5">PDF، عکس یا پاسخنامه</p>
            </div>
          </button>

          <p className="text-[12px] font-bold text-[var(--muted-2)]">نتایج قبلی</p>

          {EXAM_RESULTS.map(e => (
            <button key={e.id} onClick={() => setSelected(e.id)}
              className="w-full bg-[var(--card)] rounded-2xl border border-[var(--border)] p-4 text-right hover:border-[#E5DDD4] active:scale-[0.98] transition-all">
              <div className="flex items-start justify-between mb-3">
                <div className="text-left">
                  <p className="text-2xl font-bold text-[#C4714A]">{e.totalScore}%</p>
                  <p className="text-[11px] text-[var(--muted-2)] font-medium">رتبه #{e.rank.toLocaleString()}</p>
                </div>
                <div>
                  <p className="text-[14px] font-bold text-[var(--text)]">{e.provider}</p>
                  <p className="text-[11px] text-[var(--muted-2)] font-medium mt-0.5">{e.date}</p>
                </div>
              </div>
              <div className="w-full h-1.5 bg-[#F0EBE3] rounded-full overflow-hidden">
                <div className="h-full rounded-full bg-[#C4714A]" style={{ width: `${e.totalScore}%` }} />
              </div>
            </button>
          ))}

          {/* Trend */}
          <div className="bg-[#EAF5EC] rounded-2xl border border-[#C8E8D0] px-4 py-3 flex gap-3">
            <p className="text-[12px] text-[#3A6B48] leading-relaxed font-medium flex-1 text-right">
              نمره‌ات در دو آزمون اخیر <strong>۴.۳٪</strong> بهتر شده. فیزیک بیشترین فرصت رشد رو داره — این هفته روش تمرکز کن.
            </p>
            <span className="text-[#6B9E7A] mt-0.5 flex-shrink-0 font-bold">↑</span>
          </div>
        </div>
      ) : exam ? (
        <div className="px-5 space-y-4">
          <div className="bg-[var(--card)] rounded-3xl border border-[var(--border)] p-5">
            <div className="flex items-center justify-between mb-2">
              <div className="text-left">
                <p className="text-[11px] font-bold text-[var(--muted-2)]">رتبه‌ی کشوری</p>
                <p className="text-3xl font-bold text-[var(--text)]">#{exam.rank.toLocaleString()}</p>
              </div>
              <div className="text-right">
                <p className="text-[11px] font-bold text-[var(--muted-2)]">نمره‌ی کل</p>
                <p className="text-5xl font-bold text-[#C4714A]">{exam.totalScore}%</p>
              </div>
            </div>
          </div>

          <div className="bg-[var(--card)] rounded-3xl border border-[var(--border)] p-5">
            <p className="text-[12px] font-bold text-[var(--muted-2)] mb-4 text-right">جزئیات هر درس</p>
            <div className="space-y-4">
              {exam.subjects.map(s => (
                <div key={s.name}>
                  <div className="flex justify-between mb-1.5">
                    <div className="flex gap-3 text-[11px] font-bold" dir="ltr">
                      <span className="text-[#6B9E7A]">✓ {s.correct}</span>
                      <span className="text-[#C44A4A]">✗ {s.wrong}</span>
                      <span className="text-[var(--muted-2)]">— {s.blank}</span>
                    </div>
                    <p className="text-[13px] font-semibold text-[var(--text)]">{s.name}</p>
                  </div>
                  <ScoreBar score={s.score} />
                </div>
              ))}
            </div>
          </div>

          <div className="bg-[#FFF5F0] rounded-2xl border border-[#F5DDD0] p-4">
            <p className="text-[11px] font-bold text-[#C4714A] mb-2 text-right">تحلیل هوشمند</p>
            <p className="text-[13px] text-[#5A3A2A] leading-relaxed text-right">
              قوی‌ترین درست <strong>حسابان</strong> با ۸۲٪ هست. عربی با ۵۵٪ ضعیف‌ترین — هفته‌ای ۲ جلسه اضافه بذار. فیزیک زمان‌بندی داره — ۱۳ تا سفیدگذاشتی؛ احتمالاً وقتت تموم می‌شه.
            </p>
          </div>
        </div>
      ) : null}
    </div>
  );
}

