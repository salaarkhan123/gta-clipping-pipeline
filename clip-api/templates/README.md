# Template preview assets

One folder per template id from `app/templates.py`. Everything here is ours: drawn by our script, or rendered from footage the owner has the rights to publish. No third-party artwork, screenshots or gameplay.

| File | What it is | Where it comes from |
|---|---|---|
| `<id>/poster.svg` | A schematic of the template's layout in the ClutchClips colours, with its name, shape, length, caption style and hook. It says "layout schematic, not game footage" on it. | `python scripts/make_template_previews.py --posters` |
| `<id>/preview.mp4` | A short real clip in the template's look. None are committed yet. | `python scripts/make_template_previews.py <video> --i-have-rights` |

The public list (`GET /v1/templates`) points at these as `preview.poster` and `preview.video`, relative to the site root: `templates/<id>/poster.svg`. `preview.video` is `null` until a clip is committed and listed (below).

## Posters

Run from `clip-api/`:

```
python scripts/make_template_previews.py --posters
```

It rewrites every poster from the catalogue. Run it after adding or changing a template; a test fails when a committed poster no longer matches what the script draws.

The boxes for each layout are in `SCHEMATICS` in the script. They are our reading of the layout names. The renderer (`app/pipeline/layouts.py`) decides the real boxes: when those are final, update `SCHEMATICS` and re-run. Posters for `gameplay_a` and `gameplay_b` carry "provisional layout" because those two layouts are provisional (`PROVISIONAL_LAYOUTS` in `app/templates.py`).

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

These are static files. The site must serve this folder at `/templates/` (see the pull request's "Wiring needed").
