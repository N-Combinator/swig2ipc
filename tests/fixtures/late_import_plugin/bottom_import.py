"""A plugin whose pcbnew imports sit below the code that uses them."""


class BoardReport(pcbnew.ActionPlugin):
    def Run(self):
        board = pcbnew.GetBoard()
        pcbnew.Refresh()
        return ToMM(board.GetThickness())


import pcbnew  # noqa: E402 - late on purpose
from pcbnew import ToMM  # noqa: E402
