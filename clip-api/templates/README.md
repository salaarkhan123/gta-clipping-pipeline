# Template preview assets

One folder per template id from `app/templates.py`: the game templates and the game-type presets. Everything here is ours: drawn by our script, or rendered from footage the owner has the rights to publish. No third-party artwork, screenshots or gameplay.

| File | What it is | Where it comes from |
|---|---|---|
| `<id>/poster.svg` | A schematic of the template's layout in the ClutchClips colours, with its name and shape. A game template's shows its length, caption style and hook; a preset's shows its panel sizes and one caption word where captions sit. It says "layout schematic, not game footage" on it. | `python scripts/make_template_previews.py --posters` |
| `<id>/poster.webp` | One frame of the template's real look: the owner's own GTA footage rendered with the template's layout, panel sizes, caption style and position and hook, 360x640 WebP (640x360 for a 16:9 template), about 25 to 40 KB. Served before `poster.svg`. Templates for other games show the GTA footage in their layout until the owner supplies footage from those games. | `python scripts/make_template_previews.py "<owner's video>" --i-have-rights --poster-frames [--start 3300]` |
| `<id>/preview.mp4` | A short real clip in the template's look. None are committed yet. | `python scripts/make_template_previews.py <video> --i-have-rights` |

In the public list (`GET /v1/templates`), `preview.poster` is the path of the API route that serves the poster, `/v1/templates/<id>/poster`. `preview.video` is `templates/<id>/preview.mp4`, relative to the site root, and `null` until a clip is committed and listed (below).

## Posters

The site shows `poster.webp` (a frame of real footage) when it is there, and the drawing otherwise. The committed frames come from `GTA_Benchmark_2Hours.mkv` at 3300 s (street action with the facecam in shot), the owner's own footage. Re-run the `--poster-frames` command after changing a template's look.

The drawings: run from `clip-api/`:

```
python scripts/make_template_previews.py --posters
```

It rewrites every poster from the catalogue. Run it after adding or changing a template; a test fails when a committed poster no longer matches what the script draws.

Where the boxes come from:

- A layout with a camera panel over or under the gameplay (`split2`, `screen_first`, `gameplay_a`, `gameplay_b`, and every preset with a camera) is drawn from the template's own `panels`: where the camera is and the top panel's share of the height. Each panel is labelled with its share.
- The other layouts (`auto`, `full`, `fit`, `pip`) are in `SCHEMATICS` in the script. They are our reading of the layout names.

The renderer (`app/pipeline/layouts.py`) decides the real boxes. A test compares `LAYOUT_PANELS` in `app/templates.py` with the renderer's own numbers; when it fails, update `LAYOUT_PANELS` and re-run the script.

Posters for `gameplay_a` and `gameplay_b` carry "provisional layout" because those two layouts are provisional (`PROVISIONAL_LAYOUTS` in `app/templates.py`). Every preset's poster carries "provisional preset": which reference layout each preset matches is not confirmed.

The caption word on a preset's poster is ours (`CAPTION_WORDS` in the script). It sits on the line between the panels, or in the lower third when gameplay fills the frame, which is where the presets' caption style puts captions.

## Real preview clips

Only from video you own or have written permission to publish. We have no rights-cleared gameplay footage yet, so there are no preview clips.

```
python scripts/make_template_previews.py my-own-stream.mp4 --i-have-rights --start 754 --seconds 6
python scripts/make_template_previews.py my-own-valorant.mp4 --i-have-rights --game valorant
python scripts/make_template_previews.py clip.mp4 --i-have-rights --only cs2-clutch,cs2-frag-highlight
```

For each template it cuts `--seconds` from `--start` and renders `<id>/preview.mp4` with the template's own options (shape, caption style, layout) through the same renderer jobs use, 540 pixels on the short side. The captions are a sample line and the hook is the template's name.

Then:

1. Watch every clip.
2. Add the ids to `PREVIEW_VIDEOS` in `app/templates.py`.
3. Commit the `preview.mp4` files with that change. A test fails if a listed id has no file, or a committed clip is not listed.

Use footage of the right game for each template: a Valorant template should preview with Valorant footage.

## Serving

Posters are served by the API: `GET /v1/templates/<id>/poster` reads `<id>/poster.svg` from this folder (or `poster.webp`, `poster.png`, `poster.jpg`, in that order, when there is no SVG). The file is found from the catalogue entry, never from the text of the URL. It is sent as an image only: its own media type, `X-Content-Type-Options: nosniff`, and a content security policy that lets an SVG run no script and load nothing.

This folder must therefore be inside the API image, next to `app/` (see the pull request's "Wiring needed"). Without it the route answers 404 `no_poster`.

Preview clips are static files: when one is committed, the site must serve it at `/templates/<id>/preview.mp4`.
