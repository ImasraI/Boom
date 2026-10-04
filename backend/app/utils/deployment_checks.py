"""Configuration checks without exposing secrets or changing runtime data."""
from urllib.parse import urlsplit


def configuration_issues(settings):
    errors, warnings = [], []
    if settings.APP_ENV.strip().lower() != 'production':
        errors.append('APP_ENV must be production on the VM.')
    secret = settings.SECRET_KEY.strip()
    if len(secret) < 32 or secret.lower() in {'your-secret-key-change-me', 'change-me', 'secret', 'changeme'}:
        errors.append('SECRET_KEY must be a strong persistent secret of at least 32 characters.')
    if settings.DISABLE_AUTH or settings.SMS_DEBUG_ECHO or settings.SIGNUP_BYPASS_CODE:
        errors.append('Disable DISABLE_AUTH, SMS_DEBUG_ECHO and SIGNUP_BYPASS_CODE for production.')
    origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(',')]
    if not origins or any(not origin or origin == '*' or urlsplit(origin).scheme != 'https' or not urlsplit(origin).netloc or urlsplit(origin).path not in ('', '/') for origin in origins):
        errors.append('CORS_ORIGINS must contain explicit HTTPS frontend origins.')
    if not settings.SMS_API_KEY.strip() or not settings.SMS_VERIFY_TEMPLATE_ID.strip().isdigit():
        errors.append('Configure SMS.ir API key and numeric approved verification template ID.')
    if not settings.SMS_VERIFY_PARAMETER_NAME.strip():
        errors.append('SMS_VERIFY_PARAMETER_NAME must match the approved template placeholder.')
    if settings.SMS_TRUST_ENV:
        warnings.append('SMS_TRUST_ENV enables ambient proxies; use only when explicitly required.')
    provider = settings.LLM_PROVIDER.strip().lower()
    if provider == 'mock':
        errors.append('LLM_PROVIDER=mock is a test provider.')
    keys = {'gemini': settings.GEMINI_API_KEY, 'cerebras': settings.CEREBRAS_API_KEY, 'groq': settings.LLM_API_KEY or settings.GROQ_API_KEY}
    if provider in keys and not keys[provider].strip():
        errors.append(f'Configure credentials for the {provider} chat provider.')
    if not settings.POOL_LLM_API_KEY.strip() and not settings.POOL_LLM_PROVIDER.strip():
        warnings.append('Mock generation shares the chat provider/key and its quota.')
    if settings.EMBEDDING_PROVIDER.strip().lower() == 'gemini':
        if not (settings.EMBEDDING_API_KEY or settings.GEMINI_API_KEY).strip():
            errors.append('Configure GEMINI_API_KEY or EMBEDDING_API_KEY for hosted embeddings.')
        if settings.EMBEDDING_MODEL_NAME not in {'gemini-embedding-2', 'gemini-embedding-001'}:
            errors.append('Set a valid Gemini EMBEDDING_MODEL_NAME and rebuild incompatible vectors.')
        if not 128 <= settings.EMBEDDING_DIMENSIONS <= 3072:
            errors.append('Gemini EMBEDDING_DIMENSIONS must be between 128 and 3072.')
    return errors, warnings
