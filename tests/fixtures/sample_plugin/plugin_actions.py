import pcbnew


class BoardStats(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = "Board stats"
        self.category = "Read only"
        self.description = "Count footprints"

    def Run(self):
        board = pcbnew.GetBoard()
        count = len(board.GetFootprints())
        width = pcbnew.FromMM(0.2)
        pcbnew.SomeMysteryHelper(count, width)
        pcbnew.Refresh()


BoardStats().register()
