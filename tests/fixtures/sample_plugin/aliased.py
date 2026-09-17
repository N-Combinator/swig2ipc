import pcbnew as pcb


def load(path):
    board = pcb.LoadBoard(path)
    origin = pcb.VECTOR2I(pcb.FromMM(10), pcb.FromMM(20))
    board.SetAuxOrigin(origin)
    pcb.SaveBoard(path, board)
    return board
