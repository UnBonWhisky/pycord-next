import inspect


def _has_own_docs(cls, name):
    try:
        member = inspect.getattr_static(cls, name)
    except AttributeError:
        return False
    if type(member).__name__ == "_tuplegetter":
        return False
    return isinstance(member, property) and bool(inspect.getdoc(member))


def drop_duplicated_attributes(app, what, name, obj, options, lines):
    """Drop the napoleon ``Attributes`` entry of a property that has its own docstring.

    A property documented by ``:members:`` and listed in the ``Attributes`` section
    of the class docstring would be described twice.
    """
    if what != "class" or not inspect.isclass(obj):
        return
    kept = []
    skipping = False
    for line in lines:
        if line.startswith(".. attribute:: "):
            skipping = _has_own_docs(obj, line.removeprefix(".. attribute:: ").strip())
        elif skipping and line and not line[0].isspace():
            skipping = False
        if not skipping:
            kept.append(line)
    lines[:] = kept


def setup(app):
    app.connect("autodoc-process-docstring", drop_duplicated_attributes, priority=900)
    return {"parallel_read_safe": True, "parallel_write_safe": True}
