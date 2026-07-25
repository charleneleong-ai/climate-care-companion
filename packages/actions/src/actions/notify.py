class NotificationPolicy:
    """Track A. FR-21: dispatch on upward tier transition only — a person who has
    been High all week does not need telling again. FR-22: at most one notification
    per person per six-hour period.

    Both rules exist to protect the signal. A system that notifies on every
    assessment is one the caregiver mutes by Wednesday.
    """

    def should_notify(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("Track A owns this. See spec FR-21 and FR-22.")
