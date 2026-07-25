class ChecklistBuilder:
    """Track A. FR-19: an ordered checklist derived solely from the reason codes.

    Read rows via core.corpus.Corpus.actions_for(). Two constraints bind here:
    never re-derive risk from raw exposure (AC-2 — the reasons array is the system
    of record), and never advise altering a prescription (SC-1 — state the risk and
    route to a pharmacist or GP).
    """

    def build(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("Track A owns this. See spec FR-19.")
