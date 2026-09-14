export interface Question {
  question: string;
  options: [string, string, string, string];
  answer: number;
}

export interface SubjectTest {
  id: string;
  name: string;
  icon: string;
  color: string;
  questions: Question[];
}

export const SUBJECT_TESTS: SubjectTest[] = [
  {
    id: "calculus",
    name: "حسابان",
    icon: "∫",
    color: "#C4714A",
    questions: [
      { question: "مشتق تابع f(x) = x³ + 2x² - 5x + 1 برابر است با:", options: ["3x² + 4x - 5", "3x² + 2x - 5", "x² + 4x - 5", "3x² + 4x + 5"], answer: 0 },
      { question: "مقدار انتگرال ∫(2x + 1)dx برابر است با:", options: ["x² + x + C", "2x² + x + C", "x² + 2x + C", "2x + C"], answer: 0 },
      { question: "limit(x→0) sin(x)/x برابر است با:", options: ["1", "0", "∞", " abolished"], answer: 0 },
      { question: "مشتق ln(x²) برابر است با:", options: ["2/x", "1/x²", "2x", "x/2"], answer: 0 },
      { question: "اگر f(x) = eˣ باشد f'(x) برابر است با:", options: ["eˣ", "xeˣ⁻¹", "eˣ⁻¹", "ln(x)"], answer: 0 },
      { question: "انتگرال ∫₀¹ 2x dx برابر است با:", options: ["1", "2", "0.5", "0"], answer: 0 },
      { question: "مشتق tan(x) برابر است با:", options: ["sec²(x)", "cot(x)", "cos²(x)", "sin(x)"], answer: 0 },
      { question: "مقدار ∫cos(x)dx برابر است با:", options: ["sin(x) + C", "-cos(x) + C", "-sin(x) + C", "cos(x) + C"], answer: 0 },
      { question: "limit(x→∞) (1 + 1/x)ˣ برابر است با:", options: ["e", "1", "∞", "0"], answer: 0 },
      { question: "مشتق x·sin(x) برابر است با:", options: ["sin(x) + x·cos(x)", "cos(x)", "x·cos(x)", "sin(x) - x·cos(x)"], answer: 0 },
    ],
  },
  {
    id: "physics",
    name: "فیزیک",
    icon: "⚡",
    color: "#4A7AC4",
    questions: [
      { question: " واحد نیرو در سیستم SI کدام است؟", options: ["نیوتن", "ژول", "وات", "پاسکال"], answer: 0 },
      { question: "قانون دوم نیوتن بیان می‌کند:", options: ["F = ma", "F = mv", "F = m/v", "F = v/a"], answer: 0 },
      { question: "سرعت نور در خلأ تقریباً برابر است با:", options: ["3×10⁸ m/s", "3×10⁶ m/s", "3×10¹⁰ m/s", "3×10⁴ m/s"], answer: 0 },
      { question: "انرژی جنبشی یک جسم به فرمول زیر محاسبه می‌شود:", options: ["½mv²", "mv", "mgh", "½kx²"], answer: 0 },
      { question: "قانون اول ترمودینامیک عبارت است از:", options: ["ΔU = Q - W", "ΔU = Q + W", "ΔU = Q × W", "ΔU = Q / W"], answer: 0 },
      { question: "شدت میدان الکتریکی واحد کدام است؟", options: ["N/C یا V/m", "Tesla", "Weber", "Henry"], answer: 0 },
      { question: "مدار RL در حالت پایدار DC رفتار می‌کند مانند:", options: ["مقاومت خالص", "خازن", "سیم‌پیچ", "دیود"], answer: 0 },
      { question: "شتاب گرانشی زمین تقریباً برابر است با:", options: ["9.8 m/s²", "10.2 m/s²", "8.9 m/s²", "11 m/s²"], answer: 0 },
      { question: "فرمول دوره نوسان فنر ساده کدام است؟", options: ["T = 2π√(m/k)", "T = 2π√(k/m)", "T = 2πm/k", "T = 2πk/m"], answer: 0 },
      { question: "در اثر فوتوالکتریک، اگر فرکانس نور کمتر از آستانه باشد:", options: ["هیچ الکتریکی تولید نمی‌شود", "الکتریک با شدت بیشتر تولید می‌شود", "الکتریک با انرژی بیشتر تولید می‌شود", "هیچ‌کدام"], answer: 0 },
    ],
  },
  {
    id: "chemistry",
    name: "شیمی",
    icon: "⚗",
    color: "#7AC44A",
    questions: [
      { question: "تعداد پروتون‌های عنصر کربن چقدر است؟", options: ["6", "8", "12", "4"], answer: 0 },
      { question: "فرمول شیمیایی آب چیست؟", options: ["H₂O", "HO₂", "H₂O₂", "OH"], answer: 0 },
      { question: "pH محلولی با غلظت H⁺ برابر 10⁻³ چقدر است؟", options: ["3", "11", "7", "4"], answer: 0 },
      { question: "کدام یک از موارد زیر اسید قوی است؟", options: ["HCl", "CH₃COOH", "NH₃", "NaOH"], answer: 0 },
      { question: "قانون پاولی بیان می‌کند:", options: ["هر اوربیتال حداکثر 2 الکترون دارد", "هر اوربیتال یک الکترون دارد", "الکترون‌ها فقط در لایه اول قرار می‌گیرند", "هیچ‌کدام"], answer: 0 },
      { question: "واحد مول (mol) چند ذره است؟", options: ["6.022×10²³", "6.022×10²²", "6.022×10²⁴", "6.022×10²⁰"], answer: 0 },
      { question: "محلول با pH = 7 چگونه محلولی است؟", options: ["خنثی", "اسیدی", "بازی", "هیچ‌کدام"], answer: 0 },
      { question: "در یک واکنش اکسایش-کاهش، عامل اکسید کننده:", options: ["الکترون می‌گیرد", "الکترون می‌دهد", "هیچ‌کدام", "هر دو"], answer: 0 },
      { question: "اتم مرکزی در مولکول CH₄ چیست؟", options: ["کربن", "هیدروژن", "اکسیژن", "هیچ‌کدام"], answer: 0 },
      { question: "انرژی پیوند کووالانسی نسبت به پیوند یونی معمولاً:", options: ["بیشتر است", "کمتر است", "برابر است", "هیچ‌کدام"], answer: 0 },
    ],
  },
  {
    id: "literature",
    name: "ادبیات فارسی",
    icon: "📖",
    color: "#C44A7A",
    questions: [
      { question: "شاهنامه فردوسی در چه قرنی سروده شده است؟", options: ["چهارم و پنجم هجری", "سوم هجری", "ششم هجری", "هفتم هجری"], answer: 0 },
      { question: "قالب شعری مثنوی معنوی مولانا چیست؟", options: ["مثنوی", "غزل", "رباعی", "قصیده"], answer: 0 },
      { question: "واژه «شمس» در دیوان شمس تبریزی نماد چیست؟", options: ["عشق الهی", "خورشید", "زیبایی", "حکمت"], answer: 0 },
      { question: "کدام یک از آثار زیر از صادق هدایت است؟", options: ["بوف کور", "سووشون", "جادی‌ها", "شازده احتجاب"], answer: 0 },
      { question: " «بنی آدم اعضای یکدیگرند» از کیست؟", options: ["سعدی", "حافظ", "مولانا", "فردوسی"], answer: 0 },
      { question: "قافیه در شعر چیست؟", options: ["کلمه‌ای که در انتهای مصرع تکرار می‌شود", "کلمه‌ای که در میان مصرع می‌آید", "نوع وزن شعر", "TEMPO شعر"], answer: 0 },
      { question: " «گلستان» سعدی چه نوع اثری است؟", options: ["نثر مسجع", "شعر", "حماسه", "داستان کوتاه"], answer: 0 },
      { question: "در سطر «ز فردا چه خبر»، «فردا» نقش معنایی کدام را دارد؟", options: ["مفعول", "فاعل", "حال", "مصدری"], answer: 0 },
      { question: "«رباعی» چند مصرع دارد؟", options: ["۴", "۲", "۳", "۶"], answer: 0 },
      { question: "حافظ در اشعارش بیشتر از چه سبکی استفاده می‌کند؟", options: ["غزل عاشقانه", "حماسه", "شعر نو", "قصیده"], answer: 0 },
    ],
  },
  {
    id: "arabic",
    name: "عربی",
    icon: "ﷲ",
    color: "#C4A84A",
    questions: [
      { question: " «كِتابٌ» چه نوع اسمی است؟", options: ["مِنقوص", "مَجْرور", "مَرْفوع", "مَنْصوب"], answer: 0 },
      { question: "فعل ماضی «كَتَبَ» در جمع مذكر سالم می‌شود:", options: ["كَتَبُوا", "كَتَبْنَا", "كَتَبْتُمْ", "كَتَبْتِ"], answer: 0 },
      { question: " «ال» در «الکتاب» نشانه چیست؟", options: ["معرفه", "نکره", "تعریف", "تنکیر"], answer: 0 },
      { question: " «مِنْ» حرف جر در زبان عربی نشانه کدام مفهوم است؟", options: ["از", "به", "در", "بر"], answer: 0 },
      { question: "در جمله «ذَهَبَ الولدُ إلی المدرسهِ»، «إلی» نقش کدام را دارد؟", options: ["جار و مجرور", "فاعل", "مفعول به", "خبر"], answer: 0 },
      { question: " «لا» نفی در جمله «لا أکتُبُ» بر کدام فعل دلالت می‌کند؟", options: ["مضارع", "ماضی", "امر", "نهی"], answer: 0 },
      { question: " «حَذَفَ» یعنی چه؟", options: ["حذف کردن", "نوشتن", "خواندن", "رفتن"], answer: 0 },
      { question: " «الضارِع» شکل دیگر کدام زمان است؟", options: ["مضارع", "ماضی", "امر", "禁"], answer: 0 },
      { question: " «إنَّ» و «أَنَّ» بعد از خود چه حالتی می‌دهند؟", options: ["نصب", "رفع", "جر", "همه"], answer: 0 },
      { question: " «الْمُدَرِّسُونَ» جمع کدام کلمه است؟", options: ["المُدَرِّس", "المُدَرِّسة", "التلمیذ", "المدرسه"], answer: 0 },
    ],
  },
  {
    id: "english",
    name: "زبان انگلیسی",
    icon: "Aa",
    color: "#8A4AC4",
    questions: [
      { question: "Choose the correct form: She ___ to school every day.", options: ["goes", "go", "going", "gone"], answer: 0 },
      { question: "Which sentence is in Present Perfect?", options: ["I have eaten", "I eat", "I ate", "I will eat"], answer: 0 },
      { question: "What does 'ubiquitous' mean?", options: ["Present everywhere", "Unique", "Useful", "Understood"], answer: 0 },
      { question: "Choose the correct preposition: She is interested ___ music.", options: ["in", "on", "at", "for"], answer: 0 },
      { question: "If I ___ rich, I would travel the world.", options: ["were", "am", "will be", "have been"], answer: 0 },
      { question: "The opposite of 'ancient' is:", options: ["Modern", "Old", "Historic", "Antique"], answer: 0 },
      { question: "Which is correct? 'He has ___ finished.'", options: ["already", "yet", "since", "for"], answer: 0 },
      { question: "«Although» means the same as:", options: ["Even though", "Because", "So that", "In order to"], answer: 0 },
      { question: "Choose: There ___ many people at the party.", options: ["were", "was", "is", "has"], answer: 0 },
      { question: "The past participle of 'write' is:", options: ["written", "wrote", "writen", "writing"], answer: 0 },
    ],
  },
];
