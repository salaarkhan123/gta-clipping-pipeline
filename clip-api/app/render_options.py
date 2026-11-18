"""How a clip is framed, captioned and rendered: the options every tool shares.

Owned by the rendering agent (docs/CONTRACTS.md). The clip-finding options (count, length, language) live with
the clip routes in routes_media.py.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator

from .pipeline.layouts import NEEDS_CAMERA, layout_problem

# The reframe layouts (app/pipeline/layouts.py LAYOUTS), then the three names from before them, which keep working.
Layout = Literal["auto", "full", "fit", "split2", "trio", "grid4", "pip", "ots", "screen_first", "gameplay_a",
                 "gameplay_b", "split", "fill", "classic"]
Resolution = Literal["480", "720", "1080", "2k", "4k"]


class LayoutOptions(BaseModel):
    """How a clip is framed and captioned. Shared by every tool."""
    model_config = ConfigDict(extra="forbid")
    vertical: bool = True
    aspect: Literal["9:16", "4:5", "1:1", "16:9"] = "9:16"
    chat_region: Literal["none", "top-right", "top-center", "top-left", "bottom-right", "bottom-left"] = "none"
    zoom: float = Field(1.0, ge=1.0, le=1.6)
    captions: bool = True
    # impact: one or two big words at a time, the keyword in the accent colour. The other five highlight the word
    # being said.
    caption_style: Literal["impact", "pop", "bold", "neon", "boxed", "clean"] = "impact"
    # The next two are for the impact style; the other styles ignore them. auto: on the line between the panels
    # of a two-panel layout, in the lower third otherwise. A caption never covers the streamer's face, wherever
    # it is asked to sit.
    caption_position: Literal["auto", "seam", "lower", "center"] = "auto"
    caption_accent: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")     # null: the brand lime
    censor: bool = False          # mask swears in burned captions and subtitle downloads (f***ing)
    # The clip's thumbnail carries its hook (else its title) in big letters. Separate from hook_overlay, which is
    # the hook burned into the video: either can be on without the other. Free either way.
    thumbnail_text: bool = True
    # Which layouts an aspect offers is in layouts.ALLOWED. trio, grid4 and ots are not built yet and are refused.
    layout: Layout = "auto"
    # The two-panel layouts (split2 and the old split, screen_first, gameplay_a, gameplay_b, and auto when it
    # draws one): which panel the camera is, and the top panel's share of the height. Null keeps the layout's
    # own. In 16:9 the panels sit side by side: top is the left panel, the ratio its share of the width. Every
    # other layout ignores both.
    camera: Literal["top", "bottom"] | None = None
    split_ratio: float | None = Field(default=None, ge=0.25, le=0.75)
    # The export's short side. Never above the source's own: "4k" from a 1080p upload is a 1080p clip. Left out,
    # a clip is rendered as it always was (the 1080 canvas, whatever the source); the plan's cap always applies.
    resolution: Resolution = "1080"
    facecam_region: Literal["auto", "top-left", "top-right", "bottom-left", "bottom-right"] | None = "auto"
    facecam_box: list[float] | None = Field(default=None, min_length=4, max_length=4)

    @model_validator(mode="after")
    def check_layout(self):
        if self.facecam_box is not None:
            x, y, w, h = self.facecam_box
            if not (0 <= x < 1 and 0 <= y < 1 and 0.05 <= w <= 1 and 0.05 <= h <= 1 and x + w <= 1 and y + h <= 1):
                raise ValueError("facecam_box must be [x, y, w, h] fractions inside the frame")
        problem = layout_problem(self.layout, self.aspect)
        if problem:
            raise ValueError(problem[1])
        if self.layout in NEEDS_CAMERA and not (self.facecam_box or self.facecam_region):
            raise ValueError(f"layout '{self.layout}' needs facecam_region or facecam_box")
        return self

    @model_serializer(mode="wrap")
    def _dump(self, handler):
        """`resolution` is stored with a job only when the request sent it: a job without it renders exactly as
        before, and the option dicts the worker hands to the pipeline do not grow a key it does not know yet."""
        data = handler(self)
        if "resolution" not in self.model_fields_set:
            data.pop("resolution", None)
        return data
