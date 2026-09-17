"""The module is imported lazily, in a helper defined after its callers."""


def track_widths():
    return [pcb.ToMM(w) for w in pcb.GetBoard().GetTracks()]


def load(path):
    return pcb.LoadBoard(path)


def _setup():
    global pcb
    import pcbnew as pcb
