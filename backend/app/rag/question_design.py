"""Authoring requirements, separate from answer correctness and empirical difficulty."""
import json
from app.rag.authoring_originality import originality_contract


def authoring_contract(level):
    requirements = {
        'easy': 'یک مفهوم روشن با کاربرد مستقیم مجاز است؛ ساده بودن را پنهان نکن.',
        'konkur': 'یک تصمیم مفهومی معنادار و اتصال حداقل دو گام لازم است؛ جایگذاری مستقیم در یک اتحاد کافی نیست.',
        'hard': 'حداقل دو مفهوم مرتبط باید واقعاً در حل تعامل کنند و یک بینش ضروری وجود داشته باشد؛ حساب طولانی به تنهایی سختی نیست.',
        'extreme': 'مسئله غیرروتین اما درون کتاب باشد: از تحلیل پارامتر، شمارش جواب با قیود، استدلال معکوس یا کشف ساختار استفاده کن. حداقل دو مفهوم مرتبط و یک بینش ضروری که راه حل را عوض می‌کند لازم است. بازنویسی یک اتحاد یا محاسبه نسبت مثلثاتی از دو نسبت معلوم مردود است.',
    }
    return (originality_contract() + '\nAUTHORING_CONTRACT_V1\n' + requirements.get(level, requirements['konkur']) +
        '\nپیش از نوشتن متن، یک ایده تازه با سازوکار حل مشخص انتخاب کن. پاسخ نهایی باید حل قابل بررسی داشته باشد، نه ادعای خلاقیت. '
        'از منبع، مفاهیم و سبک طراحی را بگیر؛ اعداد، مجهول و مسیر حل نمونه را کپی نکن. '
        'صرف عوض کردن sin با tan، تغییر عدد یا جابه‌جایی گزینه، مسئله تازه نیست. '
        'قیود ربع، دامنه و علامت باید در حل نقش ضروری داشته باشند. '
        'گزینه‌های غلط از خطاهای مشخص حل ساخته شوند. پیچیدگی لفظی، عدد بزرگ و محاسبه فرسایشی جای بینش را نمی‌گیرد. '
        'اگر شواهد کتاب برای مسئله این سطح کافی نیست، questions خالی برگردان؛ سطح پایین‌تر را با برچسب سخت تحویل نده.\n')


def audit_contract(level):
    return ('\nDIFFICULTY_AUDIT_V1\nسطح درخواستی: ' + level + '\n' + authoring_contract(level) +
        '\nمستقل از برچسب و ادعای مولد، کوتاه‌ترین راه حل واقعی را بررسی کن. '
        'با یافتن راه میانبر ساده، سطح را بر اساس همان راه بسنج. علاوه بر valid و reason، '
        'فیلد difficulty_review را با این ساختار بده: '
        + json.dumps({'meets_requested': None, 'direct_substitution_only': False,
                      'interacting_concepts': ['نام مفهوم‌های واقعاً ضروری'],
                      'essential_insight': 'بینش ضروری و نقش آن در راه حل؛ یا رشته خالی',
                      'reason': 'دلیل کوتاه با اشاره به صورت سؤال'}, ensure_ascii=False)
        + '\nmeets_requested باید boolean یعنی true یا false، یا برای عدم قطعیت null باشد. '
        'valid فقط صحت علمی را بیان می‌کند؛ meets_requested جداست. تعداد خطوط حل معیار سختی نیست. '
        'این ارزیابی تخمینی مدل است، نه کالیبراسیون تجربی با دانش‌آموزان.')


def assess_difficulty(level, review):
    """None = incomplete audit, False = specific authoring mismatch; never auto-approve from labels."""
    if not isinstance(review, dict):
        return None
    result = review.get('meets_requested')
    if result is None:
        return None
    if type(result) is not bool or type(review.get('direct_substitution_only')) is not bool:
        return None
    concepts = review.get('interacting_concepts')
    if (not isinstance(concepts, list) or any(not isinstance(c, str) or not c.strip() for c in concepts)
            or not isinstance(review.get('essential_insight'), str)
            or not isinstance(review.get('reason'), str) or not review['reason'].strip()):
        return None
    if not result:
        return False
    if level != 'easy' and review['direct_substitution_only']:
        return False
    if level in ('hard', 'extreme') and (len(set(c.strip() for c in concepts)) < 2
                                       or not review['essential_insight'].strip()):
        return False
    return True
