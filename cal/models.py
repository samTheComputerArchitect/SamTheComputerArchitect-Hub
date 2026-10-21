from django.db import models


class Event(models.Model):
    """One thing on the calendar.

    The times are stored in UTC; the browser sends its own offset with every
    request, so the grid and the times are always shown in the time zone of
    the person looking at them.
    """

    REPEAT_NONE = 'none'
    REPEAT_DAILY = 'daily'
    REPEAT_WEEKLY = 'weekly'
    REPEAT_CHOICES = [
        (REPEAT_NONE, 'Does not repeat'),
        (REPEAT_DAILY, 'Every day'),
        (REPEAT_WEEKLY, 'Every week'),
    ]

    title = models.CharField(max_length=200)
    start = models.DateTimeField()
    end = models.DateTimeField()
    # an optional link - a paper, a repository, a meeting room
    url = models.URLField(max_length=500, blank=True, default='')
    repeat = models.CharField(max_length=8, choices=REPEAT_CHOICES, default=REPEAT_NONE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['start']

    def __str__(self):
        return self.title
