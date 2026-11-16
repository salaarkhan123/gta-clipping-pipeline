"""Game templates: one choice that sets how clips are found, cut and styled. Data only; add one by adding an entry.

`options` are the Clip Maker options the template recommends; a client applies them by sending them with the
template id (the dashboard does). `weights` and `transcript_bonus` tune detection (how much each signal counts,
and how much exciting words lift a moment); `judge_focus` tells the AI judge what this kind of clip is about.
Those three are attached on the server from the template id: a request cannot send them.
"""

TEMPLATES: dict[str, dict] = {
    "gta-rp-reaction": {
        "name": "GTA RP reaction", "game": "gta",
        "description": "Roleplay scenes: the argument, the funny line, the reaction. Camera on top, punchy captions.",
        "options": {"layout": "auto", "caption_style": "pop", "clip_length": 30, "tighten": True, "punch_zoom": True,
                    "flash_forward": True, "hook_overlay": True},
        "weights": {"audio": 0.7, "chat_motion": 1.0}, "transcript_bonus": 0.25,
        "judge_focus": "GTA roleplay: conversations, arguments, funny lines and the streamer's reactions. What is "
                       "said matters more than the action. A clip must make sense without the rest of the scene.",
    },
    "gta-online-chaos": {
        "name": "GTA Online chaos", "game": "gta",
        "description": "Explosions, griefing, sudden deaths. Short and loud, with zooms on the big moments.",
        "options": {"layout": "auto", "caption_style": "bold", "clip_length": 20, "tighten": True, "punch_zoom": True,
                    "flash_forward": True, "hook_overlay": True},
        "weights": {"audio": 1.0, "chat_motion": 0.8}, "transcript_bonus": 0.1,
        "judge_focus": "GTA Online chaos: explosions, griefing, fails, sudden deaths and things going wrong fast. "
                       "The moment itself matters more than the talking around it.",
    },
    "car-chase": {
        "name": "Car chase", "game": "gta",
        "description": "Police chases, escapes and stunts. Longer clips that keep the chase, clean captions.",
        "options": {"layout": "auto", "caption_style": "clean", "clip_length": 40, "tighten": False, "punch_zoom": True,
                    "flash_forward": True, "hook_overlay": True},
        "weights": {"audio": 0.9, "chat_motion": 0.8}, "transcript_bonus": 0.1,
        "judge_focus": "Car chases: police pursuits, escapes, stunts and crashes. Keep enough of the chase for the "
                       "ending to land; the crash, the jump or the getaway is the payoff.",
    },
    "heist-moments": {
        "name": "Heist moments", "game": "gta",
        "description": "Heists, robberies and shootouts: the tense part and how it ends.",
        "options": {"layout": "auto", "caption_style": "boxed", "clip_length": 45, "tighten": True, "punch_zoom": True,
                    "flash_forward": False, "hook_overlay": True},
        "weights": {"audio": 0.8, "chat_motion": 0.8}, "transcript_bonus": 0.15,
        "judge_focus": "Heists, robberies, shootouts and getaways. The best clip has the tense moment and its "
                       "outcome: the plan going wrong, the last-second escape, the payout.",
    },
    "funny-fails": {
        "name": "Funny fails", "game": "gta",
        "description": "Fails, glitches and ragdolls. Very short clips, bright captions.",
        "options": {"layout": "auto", "caption_style": "neon", "clip_length": 15, "tighten": True, "punch_zoom": True,
                    "flash_forward": False, "hook_overlay": True},
        "weights": {"audio": 1.0, "chat_motion": 0.9}, "transcript_bonus": 0.2,
        "judge_focus": "Fails, glitches, ragdoll physics and accidents, and the streamer laughing or raging at them. "
                       "Start as late as possible before the fail.",
    },
}


def public(template_id: str) -> dict:
    t = TEMPLATES[template_id]
    return {"id": template_id, "name": t["name"], "game": t["game"], "description": t["description"], "options": t["options"]}


def with_tuning(options: dict) -> dict:
    """`options` plus its template's detection tuning (weights, transcript bonus, judge focus). The options
    themselves are never changed here: a client applies a template's `options` by sending them, so what a job
    renders, and therefore what it costs, is always exactly what the request says. No template: unchanged."""
    template = TEMPLATES.get(options.get("template") or "")
    if not template:
        return options
    return {**options, "weights": template["weights"], "transcript_bonus": template["transcript_bonus"],
            "judge_focus": template["judge_focus"]}
