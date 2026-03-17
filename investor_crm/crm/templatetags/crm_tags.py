from django import forms
from django.template import Library

register = Library()


@register.filter
def is_select(field):
    """Return True if the form field uses a Select widget."""
    return isinstance(field.field.widget, (forms.Select, forms.NullBooleanSelect))


@register.filter
def is_checkbox_multiple(field):
    """Return True if the form field uses CheckboxSelectMultiple."""
    return isinstance(field.field.widget, forms.CheckboxSelectMultiple)


def _ordinal(n):
    """Return ordinal suffix for n: 1->'st', 2->'nd', 3->'rd', 4->'th', etc."""
    if 10 <= n % 100 <= 20:
        return 'th'
    return {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')


@register.filter
def investor_participants_display(log, investor):
    """Display investor participants for a MeetingLog or CallLog."""
    if hasattr(log, 'investor_participants_display'):
        return log.investor_participants_display(investor)
    return '—'


@register.filter
def date_ordinal(value):
    """Format a date as '7th March 2026'."""
    if value is None:
        return ''
    from datetime import date, datetime
    d = value.date() if isinstance(value, datetime) else value
    if isinstance(d, date):
        return f"{d.day}{_ordinal(d.day)} {d.strftime('%B %Y')}"
    return str(value)
