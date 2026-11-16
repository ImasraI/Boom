"""Display student names without exposing phone-based login identifiers."""


def public_name(user, profile=None):
    """A login phone number is private, not an arena display name."""
    name = (getattr(profile, "name", None) or "").strip()
    username = (getattr(user, "username", None) or "").strip()
    for value in (name, "" if username.startswith("guest_") else username):
        digits = "".join(c for c in value if c.isdecimal())
        if value and not (len(digits) >= 10 and all(c.isdecimal() or c in "+- ()" for c in value)):
            return value
    return f"بازیکن {user.id}"
