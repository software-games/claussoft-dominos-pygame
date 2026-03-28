import scene

ui = scene.ui

# pip_loc is a tuple of lists of tuples.  Use tuples where possible because
# lists require slightly more RAM.  For each domino die from 0 to 9 there is a
# list of the coordinates of the dots/pips.
pip_locs = (
    [()],
    [(1, 1)],
    [(0, 0), (2, 2)],
    [(0, 0), (1, 1), (2, 2)],
    [(0, 0), (2, 0), (0, 2), (2, 2)],
    [(0, 0), (0, 2), (1, 1), (2, 0), (2, 2)],
    [(0, 0), (1, 0), (2, 0), (0, 2), (1, 2), (2, 2)],
    [(0, 0), (1, 0), (2, 0), (1, 1), (0, 2), (1, 2), (2, 2)],
    [(0, 0), (1, 0), (2, 0), (0, 1), (2, 1), (0, 2), (1, 2), (2, 2)],
    [(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1), (0, 2), (1, 2), (2, 2)],
)


def domino_image(pips=(5, 6), die_size=70, fg_color="blue", bg_color="grey"):
    width = die_size * 2
    height = die_size
    with ui.ImageContext(width, height) as ctx:
        # domino is rounded rect in background color
        ui.set_color(bg_color)
        # ui.Path.rounded_rect(0, 0, width, height, height / 10).fill()
        path = ui.Path.rounded_rect(0, 0, width, height, height / 10)
        # path.line_width = 2
        path.fill()
        # pips are circles in foreground color
        ui.set_color(fg_color)
        # path.line_width = 1
        path.stroke()
        pip_size = height / 3
        b = int(height / 14)
        wh = pip_size - 2 * b
        # draw pips[0]
        for loc in pip_locs[pips[0]]:
            if loc:
                x, y = loc
                ui.Path.oval(x * pip_size + b, y * pip_size + b, wh, wh).fill()
        # draw dividing line
        path = ui.Path()
        # path.line_width = 4
        path.move_to(die_size, b)
        path.line_to(die_size, height - b)
        path.close()
        path.stroke()
        # draw pips[1]
        for loc in pip_locs[pips[1]]:
            if loc:
                x, y = loc
                ui.Path.oval(x * pip_size + b + die_size, y * pip_size + b, wh, wh).fill()
        return scene.Texture(ctx.get_image())


class Domino(scene.SpriteNode):
    def __init__(self, pips=(5, 6), die_size=70, fg_color="blue", bg_color="silver", *args, **kwargs):
        assert len(pips) == 2, "Need two pips!"  # noqa: S101
        image = domino_image(pips=pips, die_size=die_size, fg_color=fg_color, bg_color=bg_color)
        # print(image, pips)
        super().__init__(image, *args, **kwargs)
        self.pips = pips
        self.played_domino = None

    def rotate_90(self):
        self.rotation = 0 if self.rotation else scene.math.pi / 2

    def rotate_180(self):
        self.rotation += scene.math.pi
        self.rotation %= 2 * scene.math.pi
        self.pips = tuple(reversed(self.pips))

    def reset(self):
        self.rotation = 0
        self.pips = tuple(sorted(self.pips))

    @property
    def horizontal(self):
        print(f"{self.rotation=} {self.rotation % scene.math.pi=}")
        return not self.rotation % scene.math.pi

    def __str__(self):
        return f"Domino({self.pip=}), {self.rotation=}, {self.horizontal=}, {self.frame=}"


if __name__ == "__main__":

    class OneDominoScene(scene.Scene):
        def setup(self):
            die_size = min(*scene.get_screen_size()) / 2 - 16
            print(die_size)
            domino = Domino(
                pips=(5, 6),
                die_size=die_size,
                fg_color="pink",
                bg_color="green",
                parent=self,
                position=self.bounds.center(),
            )
            domino.anchor_point = (0.5, 0.5)

        def touch_began(self, touch):  # noqa: ARG002
            domino = self.children[0]
            domino.rotate_90()
            # domino.rotate_180()
            print(f"{domino=}")

    scene.run(OneDominoScene(), show_fps=False)
