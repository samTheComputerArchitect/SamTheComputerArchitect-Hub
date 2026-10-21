from django.db import models


class Meeting(models.Model):
    """One meeting.

    The call itself happens in the browser (WebRTC, peer to peer) on the
    meeting page. The Google fields hold a real meet.google.com link made
    with the Meet REST API, when the hub is connected to Google; joining
    that link opens the same meeting in Meet proper, for the people who
    are already inside the loop.
    """

    title = models.CharField(max_length=200)
    meet_uri = models.CharField(max_length=500, blank=True, default='')
    meet_code = models.CharField(max_length=100, blank=True, default='')
    space_name = models.CharField(max_length=200, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title
