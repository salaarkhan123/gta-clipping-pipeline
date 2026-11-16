"""How a clip is framed, captioned and rendered: the options every tool shares.

Owned by the rendering agent (docs/CONTRACTS.md). The clip-finding options (count, length, language) live with
the clip routes in routes_media.py.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LayoutOptions(BaseModel):
    """How a clip is framed and captioned. Shared by every tool."""
    model_config = ConfigDict(extra="forbid")
    vertical: bool = True
    aspect: Literal["9:16", "4:5", "1:1", "16:9"] = "9:16"
    chat_region: Literal["none", "top-right", "top-center", "top-left", "bottom-right", "bottom-left"] = "none"
    zoom: float = Field(1.0, ge=1.0, le=1.6)
    captions: bool = True
    caption_style: Literal["pop", "bold", "neon", "boxed", "clean"] = "pop"
    censor: bool = False          # mask swears in burned captions and subtitle downloads (f***ing)
    layout: Literal["auto", "split", "fill", "classic"] = "auto"
    facecam_region: Literal["auto", "top-left", "top-right", "bottom-left", "bottom-right"] | None = "auto"
    facecam_box: list[float] | None = Field(default=None, min_length=4, max_length=4)

    @model_validator(mode="after")
    def check_layout(self):
        if self.facecam_box is not None:
            x, y, w, h = self.facecam_box
            if not (0 <= x < 1 and 0 <= y < 1 and 0.05 <= w <= 1 and 0.05 <= h <= 1 and x + w <= 1 and y + h <= 1):
                raise ValueError("facecam_box must be [x, y, w, h] fractions inside the frame")
        if self.layout == "split" and not (self.facecam_box or self.facecam_region):
            raise ValueError("layout 'split' needs facecam_region or facecam_box")
        return self
