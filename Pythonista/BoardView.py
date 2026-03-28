#!/usr/bin/env python

"""
BoardView.py
"""

import scene

# from player import DominoPlayer, DominoRunMove
from domino import Domino

ui = scene.ui

colorBlack = colorDefault = "black"  # (0, 0, 0, 1)
colorWhite = zcolorBoneyard = "white"  # (1, 1, 1, 1)
colorGrey = colorStatus = "grey"  # (.7, .7, .7, 1)
colorRed = colorComputer = "red"  # (1, 0, 0, 1)
colorGreen = colorPlayArea = "green"  # (0, 1, 0, 1)
colorBlue = colorHuman = "blue"  # (0, 0, 1, 1)
colorCyan = colorPegboard = "cyan"  # (0, 1, 1, 1)
colorYellow = colorUnused = "yellow"  # (1, 1, 0, 1)
colorMagenta = colorBoneyard = "magenta"  # (1, 0, 1, 1)

# DominoBoardView object at 0x10f051f98>: (0.00, 0.00, 1024.00, 768.00)
# PlayAreaView object at 0x10e6fe5f8>: (102.00, 96.00, 816.00, 752.00), (510.00, 472.00)
# StatusView object at 0x10e6fee10>: (0.00, 702.00, 816.00, 50.00), (408.00, 727.00)
# BoneyardView object at 0x10f1741d0>: (0.00, 0.00, 102.00, 768.00), (51.00, 384.00)
# PegboardView object at 0x10f1744e0>: (918.00, 0.00, 102.00, 694.00), (969.00, 347.00)
# ScoreboardView object at 0x10f174dd8>: (0.00, 650.62, 108.44, 50.00), (54.22, 675.62)
# TextView object at 0x10f1740b8>: (0.00, 0.00, 54.22, 50.00), (27.11, 25.00)
# TextView object at 0x10f174048>: (54.22, 0.00, 54.22, 50.00), (81.33, 25.00)
# PlayerHandView object at 0x10f1749e8>: (102.00, 672.00, 816.00, 96.00), (510.00,720.00)
# PlayerHandView object at 0x10f174128>: (102.00, 0.00, 816.00, 96.00), (510.00, 48.00)


def DominoRunMove():
    raise NotImplementedError


class ColoredLayer(scene.ShapeNode):  # scene.Layer):
    # def __init__(self, inRect, inParent, inBgColor = colorDefault, *args, **kwargs):
    def __init__(self, frame, parent, fill_color=colorDefault, *args, **kwargs):
        x, y, w, h = frame
        super().__init__(
            ui.Path.rect(0, 0, w, h),
            anchor_point=(0, 0),
            fill_color=fill_color,
            parent=parent,
            position=(x, y),
            stroke_color="gold",
            *args,
            **kwargs,
        )
        print(f"{self.__class__.__name__} {fill_color=} {x=}, ({y=}, {w=}, {h=})")
        # self.position = inParent.bounds.center()
        # self.parent = inParent
        # print(inBgColor)
        # # self.fill_color = inBgColor
        # scene.Layer.__init__(self, inRect)
        # super(self.__class__, self).__init__(inRect)
        # inParent.add_layer(self)
        # self.stroke = colorWhite if inBgColor in (colorBlack, colorBlue) else colorWhite
        # self.stroke_weight = 1
        # self.background = inBgColor


class TextView(ColoredLayer):
    def __init__(self, frame, parent, fill_color=colorPegboard):
        super().__init__(frame, parent, fill_color=fill_color)
        # self.tint = *colorGreen
        self.text = "0"

    def set_text(self, in_text):
        self.text = str(in_text)

    def draw(self, a):
        super(self.__class__, self).draw(a)
        x, y = self.frame.center()
        scene.tint(*colorGrey)
        scene.text(self.text, x=x, y=y, font_size=18)


class ScoreboardView(ColoredLayer):
    # def __init__(self, frame, parent, fill_color=colorPegboard):
    def __init__(self, frame, parent, fill_color=colorUnused):
        super().__init__(frame, parent, fill_color=fill_color)
        # self.position = 54.22, 675.62  # inParent.position  # bounds.center()
        self.scores = (5, 10)

        width = self.frame.w / len(self.scores)
        self.text_boxes = []
        for i in range(len(self.scores)):
            rect = scene.Rect(i * width, 0, width, self.frame.h)
            self.text_boxes.append(TextView(rect, self))
        self.set_scores()

    def set_scores(self, in_scores=(0, 0)):
        self.scores = in_scores
        for i in range(len(self.scores)):
            self.text_boxes[i].set_text(self.scores[i])


class PegboardView(ColoredLayer):
    def __init__(self, frame, parent, fill_color=colorPegboard):
        super().__init__(frame, parent, fill_color=fill_color)
        # self.position = 969.00, 347.00  # inParent.bounds.center()
        self.max_score = 60
        self.square_size = self.frame.h / (self.max_score / 2 + 2)
        self.frame.w = self.square_size * 5
        # print(PegboardView, inParent.bounds, self.frame)
        # self.frame.center(self.superlayer.frame.center())

        _, y, _, h = self.square_rect(0, (self.max_score / 2) - 1)
        y -= self.frame.y - h - 5
        # h
        rect = scene.Rect(0, y, self.frame.w, 50)  # self.frame.h - y)
        print("ScoreboardView", rect)
        self.scoreboard = ScoreboardView(rect, self)
        # self.scoreboard.set_scores((5, 10))

    @classmethod
    def inset_rect(cls, in_rect, in_inset=5):
        in_rect.x += in_inset
        in_rect.y += in_inset
        in_rect.w -= in_inset * 2
        in_rect.h -= in_inset * 2
        return in_rect

    def square_rect(self, x, y):
        ss = self.square_size
        return self.inset_rect(scene.Rect(self.frame.x + x * ss, self.frame.y + y * ss, ss, ss))

    def draw(self, a=1):
        super(self.__class__, self).draw(a)
        # scene.tint(*colorGrey)
        # self.stroke = colorGrey
        for x in [0, 1, 3, 4]:
            for y in range(int(self.max_score / 2)):
                if x == 0 and y == 29:
                    print(f"{x=}, {y=}, {self.square_rect(x, y)=}")
                scene.ellipse(*self.square_rect(x, y))

    def syncView(self):
        pass


class StatusView(ColoredLayer):
    def __init__(self, frame, parent, fill_color=colorStatus):
        super().__init__(frame, parent, fill_color=fill_color)
        # self.position = inParent.bounds.center()
        # self.position = 408.00, 727.00
        self.statusText = ""

    def setStatusText(self, inStatusText=""):
        self.statusText = inStatusText

    def draw(self, a):
        super(self.__class__, self).draw(a)
        x, y = self.frame.center()
        scene.text(self.statusText, x=x, y=y, font_size=18)

    def syncView(self):
        pass


class PlayAreaView(ColoredLayer):
    def __init__(self, frame, parent, fill_color=colorPlayArea):
        super().__init__(frame, parent, fill_color=fill_color)
        # self.position = inParent.bounds.center() Node
        # self.position = 510, 472
        # self.dominoBoardView = inParent
        # ## assert parent == self.scene, '{} != {}'.format(parent, self.scene)
        # self.dominoBoardView = self.scene
        self.dominoBoard = self.scene.dominoWorld.mBoard
        statusViewRect = scene.Rect(0, self.frame.h - 50, self.frame.w, 50)
        self.statusView = StatusView(statusViewRect, self)

    def setStatusText(self, inStatusText=""):
        self.statusView.setStatusText(inStatusText)

    def getViewFromPlayed(self, inPlayedDomino):
        return self.scene.getViewFromPlayed(inPlayedDomino)

    def syncView(self):
        playedDominos = self.dominoBoard.mPlayedDominos
        if not playedDominos:
            return
        for playedDomino in playedDominos:  # sets all PlayedDomino.mDominoView
            dominoView = self.getViewFromPlayed(playedDomino)
            dominoView.frame.x = dominoView.frame.y = -1000  # move offscreen
        # dominoView = self.getViewFromPlayed(playedDominos[0])
        playedDominos[0].mDominoView.frame.center(self.frame.center())
        playedDominos[0].alignNeighbors()  # assume PlayedDomino.mDominoView set

    def findDominoByLoc(self, inLocation):
        for playedDomino in self.dominoBoard.mPlayedDominos:
            dominoView = self.getViewFromPlayed(playedDomino)
            if inLocation in dominoView.frame:
                return playedDomino
        return None


class PlayerHandView(ColoredLayer):
    first = True

    def __init__(self, frame, parent, inPlayer, fill_color=colorPlayArea):
        super().__init__(frame, parent, fill_color=fill_color)
        # self.position = 510.00, 720.00 if not self.first else 48.00  # inParent.bounds.center()
        self.first = False
        # self.dominoBoardView = inParent
        parent.dieWidth = int(self.frame.h / 2)
        self.player = inPlayer

    def syncView(self):
        dieWidth = self.scene.dieWidth
        dominoCount = len(self.player.mDominos)
        unusedPixels = int(self.frame.w - dieWidth * dominoCount)
        pixelsBetweenDominos = max(int(unusedPixels / (dominoCount + 1)), 1)
        # assert self.position == self.frame.center(), '{} != {}'.format(self.position, self.frame.center())
        # x, y = self.position  # frame.center()
        # x, y = self.frame.center()
        # y = self.frame.y
        dominoSpan = dieWidth + pixelsBetweenDominos
        x, y, _w, _h = self.frame
        y += dieWidth
        for i in range(dominoCount):
            d = self.player.mDominos[i]
            dominoLayer = self.scene.getDominoView(d)
            dominoLayer.rotate_90()
            # dominoLayer.rotation = 90
            # dominoLayer.frame.center(self.frame.center())
            # dominoLayer.frame.x = (pixelsBetweenDominos +
            #                        i * (self.dominoBoardView.dieWidth +
            #                             pixelsBetweenDominos)
            x = self.frame.x - pixelsBetweenDominos / 2 + i * dominoSpan
            dominoLayer.position = (x, y)


class BoneyardView(ColoredLayer):
    def __init__(self, frame, parent, fill_color=colorBoneyard):
        super().__init__(frame, parent, fill_color=fill_color)
        # self.position = 51.00, 384.00  # inParent.bounds.center()
        # self.dominoBoardView = inParent
        self.boneyard = parent.dominoWorld.getBoneyard()

    def syncView(self):
        dominoCount = len(self.boneyard)
        dieWidth = self.scene.dieWidth
        unusedPixels = int(self.frame.h - dieWidth * dominoCount)
        pixelsBetweenDominos = int(unusedPixels / (dominoCount + 1))
        pixelsBetweenDominos = max(pixelsBetweenDominos, 1)
        print(pixelsBetweenDominos)
        dieSpan = dieWidth + pixelsBetweenDominos
        x = self.frame.x - dieWidth - 2
        print(f"{x=}, {self.frame.x=}, {dieWidth=}")
        for i in range(dominoCount):
            d = self.boneyard[i]
            dominoLayer = self.scene.getDominoView(d)
            # dominoLayer.frame.center(self.frame.center())
            # dominoLayer.frame.y = (self.frame.y + pixelsBetweenDominos +
            #                        i * (dieWidth + pixelsBetweenDominos))
            y = self.frame.y + dieWidth / 2 + pixelsBetweenDominos * 2 + i * dieSpan
            dominoLayer.position = x, y


class DominoBoardView(scene.Scene):
    def __init__(self, inDominoWorld):
        super().__init__()
        self.dominoWorld = inDominoWorld
        # scene.run(self)

    def syncView(self):
        self.playAreaView.setStatusText(str(self.dominoWorld))
        for child in self.children:
            child.syncView()
        # for sublayer in self.root_layer.sublayers:
        #    sublayer.syncView()

    def setup(self):
        print(f"{self.bounds=}")
        # self.root_node = root_node = ColoredLayer(self.bounds, self, 'silver')
        portrait = self.bounds.w > self.bounds.h
        deltaW = 10 if portrait else 8
        deltaH = 8 if portrait else 10
        w = int(self.bounds.w / deltaW)
        h = int(self.bounds.h / deltaH)
        print(f"{deltaW=}, {deltaH=}, {w=}, {h=}")
        # exit()

        # bottomOfPlayArea = h * deltaH - 2
        # bottomOfPlayArea = self.bounds.h - 2 * deltaH
        playAreaRect = scene.Rect(w, h, w * (deltaW - 2), h * (deltaH - 2))  # bottomOfPlayArea)
        # frame = (w, h, w * (deltaW - 2), bottomOfPlayArea)
        self.playAreaView = PlayAreaView(playAreaRect, self)
        # print('bopa, par: {}, {}'.format(bottomOfPlayArea, playAreaRect))
        # exit()

        boneyardRect = scene.Rect(0, 0, w, self.bounds.h)
        self.boneyardView = BoneyardView(boneyardRect, self)

        r = playAreaRect.x + playAreaRect.w
        pegboardRect = scene.Rect(r, 0, w, self.bounds.h - 74)
        self.pegboardView = PegboardView(pegboardRect, self)

        # computerRect = scene.Rect(w, h * (deltaH - 1), playAreaRect.w, h)
        computerRect = scene.Rect(w, self.bounds.h - h, playAreaRect.w, h)
        computerPlayer = self.dominoWorld.getPlayer(1)  # DummyPlayer()
        self.computerView = PlayerHandView(computerRect, self, computerPlayer, colorComputer)

        humanRect = scene.Rect(w, 0, playAreaRect.w, h)
        humanPlayer = self.dominoWorld.getPlayer(0)  # DummyPlayer()
        self.humanView = PlayerHandView(humanRect, self, humanPlayer, colorHuman)

        self.dominoViews = self.makeDictOfDominoViews()
        self.syncView()

    def makeDictOfDominoViews(self):
        theDict = {}  # dict()
        for theDomino in self.dominoWorld.mDominos:
            domino = Domino(pips=theDomino, die_size=self.dieWidth, parent=self.humanView)
            theDict[tuple(theDomino)] = domino
            # dominoLayer = DominoView.DominoLayer(theDomino, self.dieWidth)
            # self.humanView.add_layer(dominoLayer) # add to the (0, 0) layer and move later
            # theDict[tuple(theDomino)] = dominoLayer
        return theDict

    def getDominoView(self, inValues):
        return self.dominoViews[tuple(sorted(inValues))]

    def getViewFromPlayed(self, inPlayedDomino):
        if not inPlayedDomino.mDominoView:  # if it is not set then set it
            # inPlayedDomino.mDominoView = self.getDominoView(inPlayedDomino.getValues())
            inPlayedDomino.setDominoView(self.getDominoView(inPlayedDomino.pips))  # getValues()))
        return inPlayedDomino.mDominoView  # and return it

    def getPlayedDominos(self):
        return self.dominoWorld.mBoard.mPlayedDominos

    def draw(self):
        # Update and draw our root layer. For a layer-based scene, this
        # is usually all you have to do in the draw method.
        # scene.background(0.7, 0.7, 0.7)
        # scene.background(1, 0, 0)
        scene.background("silver")
        # self.root_layer.update(self.dt)
        # self.root_layer.draw()
        self.drawText()
        # self.fill_color = colorBlue
        # scene.ellipse(0, 0, 128, 128)

    def drawText(
        self,
        inText="To start a game...\n\n   drag a domino from the blue player's hand and drop it here...",
    ):
        if not self.getPlayedDominos():
            x, y = self.bounds.center()
            scene.text(inText, x=x, y=y, font_size=18)

    def touch_began(self, touch):
        self.touchedLayer = None
        # print(touch.layer.__class__)
        # if isinstance(touch.layer, Domino):  # DominoView.DominoLayer):
        # print(self.dominoViews)
        for domino in self.dominoViews.values():
            if touch.location in domino.frame:
                print("got one")
                self.touchedLayer = domino  # touch.layer
                self.saveLoc = domino.position  # self.touchedLayer.getLoc()

    def touch_moved(self, touch):
        if self.touchedLayer:
            # self.touchedLayer.frame.center(touch.location)
            self.touchedLayer.position = touch.location

    def touch_ended(self, touch):
        if not self.touchedLayer:
            return
        if touch.location not in self.playAreaView.frame:
            # self.touchedLayer.setLoc(self.saveLoc)
            self.touchedLayer.position = self.saveLoc
            return
        dominoValues = self.touchedLayer.pips  # getValues()
        if self.getPlayedDominos():
            dominoDroppedOn = self.playAreaView.findDominoByLoc(touch.location)
            print(f"{dominoDroppedOn=}")
            if dominoDroppedOn and dominoDroppedOn.isPossibleNeighbor(dominoValues):
                theMove = DominoRunMove(dominoDroppedOn, dominoValues, -1)
                self.dominoWorld.playAMove(theMove)
            else:
                print("Invalid move!!!")
                self.touchedLayer.setLoc(self.saveLoc)
        else:  # firstDominoPlayed
            totalValue = sum(dominoValues)
            thePoints = 0 if totalValue % 5 else totalValue / 5
            theMove = DominoRunMove(None, dominoValues, thePoints)
            self.dominoWorld.playAMove(theMove)
            isDouble = dominoValues[0] == dominoValues[1]
            # self.touchedLayer.rotation = 90 if isDouble else 0
            if isDouble:
                self.touchedLayer.rotate_90()
        self.syncView()


if __name__ == "__main__":
    from world import DominoWorld

    scene.run(DominoBoardView(DominoWorld()), show_fps=False)
    # import world as DominoWorld
    # reload(DominoWorld)
    # DominoWorld.main()
