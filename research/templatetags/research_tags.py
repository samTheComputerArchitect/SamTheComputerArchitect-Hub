from django import template

register = template.Library()


@register.filter
def truncate_chars(value, limit):
    """Truncate to `limit` characters and append three dots."""
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return value
    text = (value or '').strip()
    if limit < 0:
        return ''
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + '...'


@register.filter
def get_item(mapping, key):
    """Look up a key in a dictionary (used for the filter urls / colours)."""
    if mapping is None:
        return ''
    try:
        return mapping.get(key, '')
    except AttributeError:
        return ''
