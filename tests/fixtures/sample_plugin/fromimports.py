from pcbnew import ActionPlugin as BasePlugin
from pcbnew import GetBoard, ToMM


class TrackReport(BasePlugin):
    def Run(self):
        board = GetBoard()
        for track in board.GetTracks():
            print(ToMM(track.GetWidth()))
