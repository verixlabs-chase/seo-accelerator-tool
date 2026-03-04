def ensure_enum(value, enum_cls):
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, str):
        return enum_cls(value)
    raise TypeError(f"Invalid enum value: {value}")

