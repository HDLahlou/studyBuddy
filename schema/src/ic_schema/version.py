"""Contract version.

Format is "MAJOR.MINOR". A MAJOR change is incompatible (the engine rejects it in `hello`);
a MINOR change only adds optional fields. Bump this and update `fixtures/` in the same change.
"""

SCHEMA_VERSION = "1.0"


def major(version: str) -> int:
    return int(version.split(".", 1)[0])


def is_compatible(version: str) -> bool:
    try:
        return major(version) == major(SCHEMA_VERSION)
    except ValueError:
        return False
