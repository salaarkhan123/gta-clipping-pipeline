"""How a clip is framed, captioned and rendered: the options every tool shares.

Owned by the rendering agent (docs/CONTRACTS.md). The clip-finding options (count, length, language) live with
the clip routes in routes_media.py.
"""
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator
from pydantic_core import PydanticCustomError

from .config import get_settings
from .pipeline.layouts import ALLOWED, NEEDS_CAMERA, layout_problem

# The reframe layouts (app/pipeline/layouts.py LAYOUTS), then the three names from before them, which keep working.
Layout = Literal["auto", "full", "fit", "split2", "trio", "grid4", "pip", "ots", "screen_first", "gameplay_a",
                 "gameplay_b", "split", "fill", "classic"]
Resolution = Literal["480", "720", "1080", "2k", "4k"]
# pipeline/captions.py: impact, the five word-highlight styles, then STYLED.
CaptionStyle = Literal["impact", "pop", "bold", "neon", "boxed", "clean",
                       "bounce", "karaoke", "reveal", "outline", "subtitle", "tag"]
# How the AI writes the on-screen hook (templates.HOOK_STYLES holds the same names).
HookStyle = Literal["serious", "casual", "informative", "conversational", "humorous", "parody", "inspirational",
                    "dramatic", "empathetic", "persuasive", "neutral", "excited", "calm"]
# full: every clip rendered at the chosen resolution. preview: a fast, small render (540 on the short side) to
# look at first; POST /v1/clips/export makes the full one. none: no video at all, only the clips' times, titles,
# scores and a thumbnail, also exported later.
RenderMode = Literal["none", "preview", "full"]
# Stored with a job only when the request sent them: a job without them renders exactly as before, and the option
# dicts the worker hands to the pipeline do not grow keys it does not know.
ONLY_WHEN_SENT = ("resolution", "render", "hook_style", "hook_position", "hook_duration_ms", "caption_look",
                  "transcribe_whole")
# Built but not yet checked on real gaming footage: offered only with PROVISIONAL_LAYOUTS on (DEPLOY.md). The
# same setting turns on the auto layout chosen per moment (facecam.moment_facecam).
PROVISIONAL = ("trio", "grid4", "ots")
NOT_AVAILABLE = "layout_not_available"


def provisional_on() -> bool:
    return get_settings().provisional_layouts


def refused_layout(errors: list[dict]) -> tuple[str, str] | None:
    """(code, message) when a validation error is a provisional layout asked for while they are off: a 400."""
    for e in errors:
        if e.get("type") == NOT_AVAILABLE:
            return NOT_AVAILABLE, e.get("msg", "This layout is not available.")
    return None


HEX = r"^#[0-9A-Fa-f]{6}$"
# The caption fonts we ship (pipeline/fonts.py FAMILIES), or an account's own: "custom:<font id>" (GET /v1/fonts).
CaptionFont = Literal["anton", "bebas", "bangers", "luckiest", "poppins"]


class CaptionLook(BaseModel):
    """How impact captions look, beyond the style: every field left out keeps the style's own. The same look is
    drawn in a preview and in the export (one renderer). Owned by the captions agent (docs/CONTRACTS.md)."""
    model_config = ConfigDict(extra="forbid")
    font: CaptionFont | str | None = Field(default=None, max_length=64)    # a family above, or "custom:<id>"
    weight: Literal["regular", "bold", "black"] | None = None     # the family's nearest file; others are emboldened
    italic: bool = False
    underline: bool = False
    colour: str | None = Field(default=None, pattern=HEX)          # the letters (null: white)
    outline_colour: str | None = Field(default=None, pattern=HEX)  # the outline (null: black)
    size: int | None = Field(default=None, ge=50, le=200)         # % of the style's size (100 = 6% of the height)
    case: Literal["upper", "as_typed"] = "upper"
    y: float | None = Field(default=None, ge=0.05, le=0.92)       # the caption's row, a share of the height;
    #                                                               null: caption_position. Never on the face or HUD.

    @model_validator(mode="after")
    def check_font(self):
        if isinstance(self.font, str) and self.font not in CaptionFont.__args__ and \
                not re.fullmatch(r"custom:[A-Za-z0-9_-]{6,40}", self.font):
            raise ValueError(f"caption_look.font must be one of {', '.join(CaptionFont.__args__)} or custom:<font id>")
        return self


class LayoutOptions(BaseModel):
    """How a clip is framed and captioned. Shared by every tool."""
    model_config = ConfigDict(extra="forbid")
    vertical: bool = True
    aspect: Literal["9:16", "4:5", "1:1", "16:9"] = "9:16"
    chat_region: Literal["none", "top-right", "top-center", "top-left", "bottom-right", "bottom-left"] = "none"
    zoom: float = Field(1.0, ge=1.0, le=1.6)
    captions: bool = True
    # impact: one or two big words at a time, the keyword in the accent colour. pop, bold, neon, boxed and clean
    # highlight the word being said. bounce: the word being said grows in; karaoke: the line fills with colour as
    # it is said; reveal: words appear one at a time; outline: a still line with a heavy outline; subtitle: a
    # still sentence-case line on a dark bar; tag: lower case with a box behind the keyword.
    caption_style: CaptionStyle = "impact"
    # The next two are for the impact style; the other styles ignore them. auto: on the line between the panels
    # of a two-panel layout, in the lower third otherwise. A caption never covers the streamer's face, wherever
    # it is asked to sit.
    caption_position: Literal["auto", "seam", "lower", "center"] = "auto"
    caption_accent: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")     # null: the brand lime
    caption_look: CaptionLook | None = None     # font, weight, italic, underline, colours, size, case, row (impact)
    censor: bool = False          # mask swears in burned captions and subtitle downloads (f***ing)
    # The clip's thumbnail carries its hook (else its title) in big letters. Separate from hook_overlay, which is
    # the hook burned into the video: either can be on without the other. Free either way.
    thumbnail_text: bool = True
    # Which layouts an aspect offers is in layouts.ALLOWED. trio, grid4 and ots are provisional (our own reading of the
    # names), offered only with PROVISIONAL_LAYOUTS on; with it on, auto also picks per moment.
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
    render: RenderMode = "full"   # clip jobs; Reframe and Captions always render in full
    # The on-screen hook (clip jobs and exports): the tone the AI writes it in, where it shows, and for how long
    # (null: 2.5 s). hook_style changes the AI's wording only, never what a job costs.
    hook_style: HookStyle = "serious"
    hook_position: Literal["beginning", "end"] = "beginning"
    hook_duration_ms: int | None = Field(default=None, ge=500, le=10000)
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
        if self.layout in PROVISIONAL and not provisional_on():
            usable = ", ".join(x for x in ALLOWED[self.aspect] if x not in PROVISIONAL)
            raise PydanticCustomError(NOT_AVAILABLE, "The {layout} layout is not available yet. Use one of: {usable}.",
                                      {"layout": self.layout, "usable": usable})
        if self.layout in NEEDS_CAMERA and not (self.facecam_box or self.facecam_region):
            raise ValueError(f"layout '{self.layout}' needs facecam_region or facecam_box")
        return self

    @model_serializer(mode="wrap")
    def _dump(self, handler):
        """The ONLY_WHEN_SENT options are stored only when the request sent them."""
        data = handler(self)
        for name in ONLY_WHEN_SENT:
            if name not in self.model_fields_set:
                data.pop(name, None)
        return data
