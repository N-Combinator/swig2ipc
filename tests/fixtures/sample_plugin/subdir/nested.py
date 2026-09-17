from pcbnew import *
from pcbnew import ZONE


def zones(board):
    return [z for z in board.GetZones() if isinstance(z, ZONE)]
