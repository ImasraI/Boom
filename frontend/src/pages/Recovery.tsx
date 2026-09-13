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

function ScaleRow({ label, value, onChange, low, high }: {
  label: string; value: number; onChange: (v: number) => void; low: string; high: string;
}) {
  return (
    <div className="py-4 border-b border-[var(--border)] last:border-0">
      <div className="flex justify-between mb-3">
        <span className="text-[13px] font-bold text-[#C4714A]">{value}/۵</span>
        <p className="text-[14px] font-semibold text-[var(--text)]">{label}</p>
      </div>
      <input type="range" min={1} max={5} step={1} value={value}
        onChange={e => onChange(Number(e.target.value))} className="w-full" />
      <div className="flex justify-between mt-1">
        <span className="text-[11px] text-[var(--muted-2)] font-medium">{low}</span>
        <span className="text-[11px] text-[var(--muted-2)] font-medium">{high}</span>
      </div>
    </div>
  );
}

const MOODS = [
  { emoji: "🌘", label: "خسته" },
  { emoji: "🌥️", label: "ضعیف" },
  { emoji: "🌤️", label: "معمولی" },
  { emoji: "☀️", label: "خوب" },
  { emoji: "✨", label: "عالی" },
];

export default function Recovery({ nav }: { nav: NavFn }) {
  const [sleep, setSleep] = useState(7);
  const [sleepQuality, setSleepQuality] = useState(3);
  const [mood, setMood] = useState(3);
  const [energy, setEnergy] = useState(3);
  const [stress, setStress] = useState(2);
  const [notes, setNotes] = useState("");
  const [saved, setSaved] = useState(false);

  return (
    <div className="min-h-screen bg-[#F8F6F2] pb-10">
      <div className="px-5 pt-12 pb-4 flex items-center gap-4">
        <BackButton onClick={() => nav("home")} />
        <div className="text-right">
          <h1 className="font-display text-xl text-[var(--text)]">چک‌این ریکاوری</h1>
          <p className="text-[12px] text-[var(--muted-2)] font-medium">امروز چه حالی داری؟</p>
        </div>
      </div>

      <div className="px-5 mt-2 space-y-4">
        {/* Mood */}
        <div className="bg-[var(--card)] rounded-3xl border border-[var(--border)] p-5">
          <p className="text-[12px] font-bold text-[var(--muted-2)] mb-4 text-right">خلق‌وخوی کلی</p>
          <div className="flex gap-2 justify-between">
            {MOODS.map((m, i) => (
              <button key={i} onClick={() => setMood(i + 1)}
                className={`flex-1 flex flex-col items-center gap-1 py-3 rounded-2xl transition-all ${
                  mood === i + 1 ? "bg-[#FFF5F0] ring-2 ring-[#C4714A]" : "bg-[#FAFAF8] hover:bg-[#F5F0EA]"
                }`}
              >
                <span className="text-2xl">{m.emoji}</span>
                <span className={`text-[9px] font-bold ${mood === i + 1 ? "text-[#C4714A]" : "text-[var(--muted-2)]"}`}>{m.label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Sleep */}
        <div className="bg-[var(--card)] rounded-3xl border border-[var(--border)] p-5">
          <p className="text-[12px] font-bold text-[var(--muted-2)] mb-1 text-right">خواب</p>
          <div className="py-4 border-b border-[var(--border)]">
            <div className="flex justify-between mb-3">
              <span className="text-[13px] font-bold text-[#C4714A]">{sleep} ساعت</span>
              <p className="text-[14px] font-semibold text-[var(--text)]">ساعت خواب دیشب</p>
            </div>
            <input type="range" min={3} max={12} step={0.5} value={sleep}
              onChange={e => setSleep(Number(e.target.value))} className="w-full" />
            <div className="flex justify-between mt-1">
              <span className="text-[11px] text-[var(--muted-2)]">۳ ساعت</span>
              <span className="text-[11px] text-[var(--muted-2)]">۱۲ ساعت</span>
            </div>
          </div>
          <ScaleRow label="کیفیت خواب" value={sleepQuality} onChange={setSleepQuality} low="خیلی بد" high="عالی" />
        </div>

        {/* Energy & stress */}
        <div className="bg-[var(--card)] rounded-3xl border border-[var(--border)] p-5">
          <p className="text-[12px] font-bold text-[var(--muted-2)] mb-1 text-right">وضعیت ذهنی</p>
          <ScaleRow label="سطح انرژی" value={energy} onChange={setEnergy} low="خسته" high="پرانرژی" />
          <ScaleRow label="سطح استرس" value={stress} onChange={setStress} low="آرام" high="خیلی استرس‌زا" />
        </div>

        {/* Notes */}
        <div className="bg-[var(--card)] rounded-3xl border border-[var(--border)] p-5">
          <p className="text-[12px] font-bold text-[var(--muted-2)] mb-3 text-right">چیز دیگه‌ای هست؟</p>
          <textarea value={notes} onChange={e => setNotes(e.target.value)}
            placeholder="مثلاً سردرد دارم، نگران آزمون فردام، صبح تمرکز داشتم..."
            rows={3}
            className="w-full bg-[#FAFAF8] rounded-xl border border-[var(--border)] px-4 py-3 outline-none text-[13px] text-[var(--text)] placeholder:text-[#C4B8A8] resize-none font-medium text-right"
          />
        </div>

        {/* AI note */}
        <div className="bg-[#FFF5F0] rounded-2xl border border-[#F5DDD0] px-4 py-3 flex gap-3">
          <p className="text-[12px] text-[var(--muted)] leading-relaxed flex-1 text-right">
            <span className="font-bold text-[#C4714A]">نکته هوشمند:</span> سه روز پشت سر هم استرس بالا گزارش دادی. برنامه‌ی فردا سبک‌تر می‌شه و یه استراحت ۲۰ دقیقه‌ای بینش اضافه می‌کنم.
          </p>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#C4714A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="mt-0.5 flex-shrink-0">
            <circle cx="12" cy="12" r="10"/><path d="M12 8v4"/><path d="M12 16h.01"/>
          </svg>
        </div>

        <button onClick={() => { setSaved(true); setTimeout(() => setSaved(false), 2000); }}
          className={`w-full py-4 rounded-2xl font-bold text-[14px] transition-all active:scale-95 ${
            saved ? "bg-[#6B9E7A] text-white" : "bg-[#C4714A] text-[#F8F6F2] hover:bg-[#A85C38]"
          }`}
        >
          {saved ? "✓ ثبت شد — برنامه‌ات آپدیت شد" : "ذخیره چک‌این"}
        </button>
      </div>
    </div>
  );
}

