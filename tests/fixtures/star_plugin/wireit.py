"""The common legacy shape: a star import plus a bare ActionPlugin base."""

from pcbnew import *


def GetTracks(board):
    """Shadows a SWIG name: this is the plugin's own helper, not pcbnew's."""
    return board.tracks


class StarPlugin(ActionPlugin):
    def defaults(self):
        self.name = "Star"
        self.category = "Test"

    def Run(self):
        board = GetBoard()
        SaveBoard("out.kicad_pcb", board)
        return GetTracks(board)


StarPlugin().register()
