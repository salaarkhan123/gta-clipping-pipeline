"""Game templates: one choice that sets how clips are found, cut and styled. Data only; add one by adding an entry.

The format is in docs/CONTRACTS.md ("Template format"). Every template has:

- `layout`, `aspect`, `caption_style`, `duration` and `hook`: what the template looks like, in the parity
  vocabulary (layouts from app/pipeline/layouts.py, length buckets, the 13 hook styles).
- `options`: the Clip Maker options the template recommends, using only fields `POST /v1/clips` accepts today.
  A client applies them by sending them with the template id (the dashboard does). The server never fills
  them in, so a template id alone cannot change what a job renders or costs.
- `weights` and `transcript_bonus` tune detection (how much each signal counts, and how much exciting words
  lift a moment); `judge_focus` tells the AI judge what this kind of clip is about. Those three are attached
  on the server from the template id: a request cannot send them and the public list never shows them.
- `preview`: our own assets under clip-api/templates/<id>/ (see the README there).
"""

GAMES = ("lol", "gta5", "wow", "ow2", "minecraft", "apex", "valorant", "fortnite", "dota2", "rust", "cs2", "other")
GAME_NAMES = {
    "lol": "League of Legends", "gta5": "GTA 5", "wow": "World of Warcraft", "ow2": "Overwatch 2",
    "minecraft": "Minecraft", "apex": "Apex Legends", "valorant": "Valorant", "fortnite": "Fortnite",
    "dota2": "Dota 2", "rust": "Rust", "cs2": "Counter-Strike 2", "other": "Other games",
}
GENRES = ("moba", "open_world", "roleplay", "racing", "mmo", "hero_shooter", "tactical_shooter", "battle_royale",
          "sandbox", "survival", "variety")

# The layouts a template may name: the ones the render agent is building. trio, grid4 and ots are not built.
LAYOUTS = ("auto", "full", "fit", "split2", "pip", "screen_first", "gameplay_a", "gameplay_b")
ASPECTS = ("9:16", "4:5", "1:1", "16:9")
CAPTION_STYLES = ("pop", "bold", "neon", "boxed", "clean")          # the keys of pipeline/captions.py CAPTION_STYLES
DURATIONS = {"0-30": (0, 30), "0-90": (0, 90), "30-60": (30, 60), "60-90": (60, 90), "90-180": (90, 180),
             "180-300": (180, 300)}
HOOK_STYLES = ("serious", "casual", "informative", "conversational", "humorous", "parody", "inspirational",
               "dramatic", "empathetic", "persuasive", "neutral", "excited", "calm")
HOOK_POSITIONS = ("beginning", "end")

# Today's `options.layout` (auto, split, fill, classic) for each template layout, until POST /v1/clips takes
# the new names. Layouts with no equivalent yet fall back to auto: camera on top when one is found.
TODAY_LAYOUT = {"auto": "auto", "full": "fill", "fit": "classic", "split2": "split", "pip": "auto",
                "screen_first": "auto", "gameplay_a": "auto", "gameplay_b": "auto"}
MAX_CLIP_LENGTH = 60        # the longest `clip_length` POST /v1/clips takes today
JUDGE_FOCUS_MAX = 400       # app/ai.py sends the judge this many characters of the focus and drops the rest

PUBLIC_FIELDS = ("id", "name", "game", "genre", "description", "layout", "aspect", "caption_style", "duration",
                 "hook", "options", "preview")
TUNING_FIELDS = ("weights", "transcript_bonus", "judge_focus")

# Ids whose rights-cleared preview clip is committed at clip-api/templates/<id>/preview.mp4
# (rendered by scripts/make_template_previews.py). Empty until the owner supplies footage.
PREVIEW_VIDEOS: frozenset[str] = frozenset()


def _template(template_id: str, name: str, game: str, genre: str, description: str, *, layout: str, caption_style: str,
              duration: str, clip_length: int, hook: str, audio: float, chat: float, bonus: float, focus: str,
              aspect: str = "9:16", tighten: bool = True, punch_zoom: bool = True, flash_forward: bool = True,
              hook_enabled: bool = True, hook_position: str = "beginning", hook_ms: int = 2500) -> dict:
    """One catalogue entry. `options` is derived from the look so the two cannot disagree."""
    options = {"layout": TODAY_LAYOUT[layout], "caption_style": caption_style, "clip_length": clip_length,
               "tighten": tighten, "punch_zoom": punch_zoom, "flash_forward": flash_forward, "hook_overlay": hook_enabled}
    if aspect != "9:16":            # 9:16 is the API default; only a different shape needs sending
        options["aspect"] = aspect
    return {
        "id": template_id, "name": name, "game": game, "genre": genre, "description": description,
        "layout": layout, "aspect": aspect, "caption_style": caption_style, "duration": duration,
        "hook": {"enabled": hook_enabled, "style": hook, "position": hook_position, "duration_ms": hook_ms},
        "options": options,
        "weights": {"audio": audio, "chat_motion": chat}, "transcript_bonus": bonus, "judge_focus": focus,
        "preview": {"video": f"templates/{template_id}/preview.mp4" if template_id in PREVIEW_VIDEOS else None,
                    "poster": f"templates/{template_id}/poster.svg"},
    }


_CATALOGUE = [
    # League of Legends
    _template(
        "lol-teamfight", "Team fight to ace", "lol", "moba",
        "The whole fight from the engage to the result. The screen stays big so the fight is readable.",
        layout="screen_first", caption_style="clean", duration="30-60", clip_length=45, tighten=False,
        punch_zoom=False, hook="informative", hook_ms=3000, audio=0.9, chat=0.9, bonus=0.1,
        focus="League of Legends team fights: 5v5s and skirmishes at Baron, dragon, Elder, turrets or the Nexus. "
              "A good clip has the engage (flash, ultimate, pick), the fight and its result: ace, shutdown, "
              "objective taken or stolen. Multi-kill announcer lines and shouting mark the peak. Skip laning, "
              "farming, shopping, recalls and grey death screens."),
    _template(
        "lol-outplay", "Solo outplay", "lol", "moba",
        "One player's mechanics: the dodge, the flash, the escape on no health. Short, with a zoom on the play.",
        layout="gameplay_a", caption_style="pop", duration="0-30", clip_length=20, flash_forward=False,
        hook="excited", hook_ms=2000, audio=1.0, chat=0.9, bonus=0.2,
        focus="League of Legends solo plays: 1v1 and 1v2 outplays, dodged skillshots, flash plays, escapes on a "
              "sliver of health, tower dives that work, smite steals, quadra and pentakills. Start just before "
              "the fight and end on the kill or the escape; the streamer's shout is the payoff. One player's "
              "mechanics matter more than the team fight around them."),
    _template(
        "lol-voice-comms", "Rift voice comms", "lol", "moba",
        "What the team says: tilt, blame, bad calls and the reaction to a throw. Camera on top, big captions.",
        layout="split2", caption_style="bold", duration="0-90", clip_length=35, punch_zoom=False,
        hook="humorous", audio=0.6, chat=1.0, bonus=0.3,
        focus="League of Legends voice comms: what the team says matters more than the play. Funny calls, blame, "
              "tilt, shotcalling that goes wrong, a duo arguing, the reaction to a throw or a steal. The clip "
              "must make sense on its own: keep the line that sets it up and the reply. Skip quiet laning and "
              "plain callouts with no punchline."),

    # GTA 5. The first five ids are in use: their options and tuning must not change.
    _template(
        "gta-rp-reaction", "GTA RP reaction", "gta5", "roleplay",
        "Roleplay scenes: the argument, the funny line, the reaction. Camera on top, punchy captions.",
        layout="auto", caption_style="pop", duration="30-60", clip_length=30, hook="conversational",
        audio=0.7, chat=1.0, bonus=0.25,
        focus="GTA roleplay: conversations, arguments, funny lines and the streamer's reactions. What is "
              "said matters more than the action. A clip must make sense without the rest of the scene."),
    _template(
        "gta-online-chaos", "GTA Online chaos", "gta5", "open_world",
        "Explosions, griefing, sudden deaths. Short and loud, with zooms on the big moments.",
        layout="auto", caption_style="bold", duration="0-30", clip_length=20, hook="excited",
        audio=1.0, chat=0.8, bonus=0.1,
        focus="GTA Online chaos: explosions, griefing, fails, sudden deaths and things going wrong fast. "
              "The moment itself matters more than the talking around it."),
    _template(
        "car-chase", "Car chase", "gta5", "racing",
        "Police chases, escapes and stunts. Longer clips that keep the chase, clean captions.",
        layout="auto", caption_style="clean", duration="30-60", clip_length=40, tighten=False, hook="dramatic",
        audio=0.9, chat=0.8, bonus=0.1,
        focus="Car chases: police pursuits, escapes, stunts and crashes. Keep enough of the chase for the "
              "ending to land; the crash, the jump or the getaway is the payoff."),
    _template(
        "heist-moments", "Heist moments", "gta5", "open_world",
        "Heists, robberies and shootouts: the tense part and how it ends.",
        layout="auto", caption_style="boxed", duration="30-60", clip_length=45, flash_forward=False, hook="serious",
        audio=0.8, chat=0.8, bonus=0.15,
        focus="Heists, robberies, shootouts and getaways. The best clip has the tense moment and its "
              "outcome: the plan going wrong, the last-second escape, the payout."),
    _template(
        "funny-fails", "Funny fails", "gta5", "open_world",
        "Fails, glitches and ragdolls. Very short clips, bright captions.",
        layout="auto", caption_style="neon", duration="0-30", clip_length=15, flash_forward=False, hook="humorous",
        audio=1.0, chat=0.9, bonus=0.2,
        focus="Fails, glitches, ragdoll physics and accidents, and the streamer laughing or raging at them. "
              "Start as late as possible before the fail."),
    _template(
        "gta5-street-race", "Street race and stunts", "gta5", "racing",
        "Races and stunt runs kept whole, from the run-up to the finish line or the wipeout.",
        layout="gameplay_a", caption_style="bold", duration="0-90", clip_length=50, tighten=False,
        flash_forward=False, hook="excited", audio=1.0, chat=0.7, bonus=0.1,
        focus="GTA races and stunt runs: street races, stunt jumps, near misses in traffic, overtakes, photo "
              "finishes, wipeouts on the last corner. Speed and a clear finish matter: keep the run-up and the "
              "landing, crash or finish line. Skip the lobby, the countdown wait and long straights where "
              "nothing happens."),

    # World of Warcraft
    _template(
        "wow-boss-kill", "Raid boss kill", "wow", "mmo",
        "The last phase of a boss through the kill or the wipe, in widescreen so the whole raid UI stays in view.",
        layout="full", aspect="16:9", caption_style="clean", duration="90-180", clip_length=60, tighten=False,
        punch_zoom=False, hook="dramatic", hook_ms=3000, audio=0.9, chat=1.0, bonus=0.2,
        focus="World of Warcraft raid and dungeon bosses: the last percent of the boss's health, a wipe at 1%, "
              "a first kill, one player left alive finishing it. Voice comms calling mechanics, then the scream "
              "at the kill or the groan at the wipe. Keep the final phase through the result and the loot. "
              "Skip trash pulls, buffing, ready checks and running back."),
    _template(
        "wow-arena-burst", "Arena burst", "wow", "mmo",
        "PvP kills in a few seconds: the burst, the clutch heal, the interrupt that wins it.",
        layout="gameplay_b", caption_style="bold", duration="0-30", clip_length=25, flash_forward=False,
        hook="excited", hook_ms=2000, audio=1.0, chat=0.8, bonus=0.1,
        focus="World of Warcraft PvP: arena and battleground fights. Burst windows that delete a health bar, "
              "clutch heals and interrupts, a 1v2 won, a kill on a sliver of health, a cooldown trade that "
              "decides the match. Start as the go begins, end on the kill or the scoreboard. Skip the gates "
              "countdown, drinking and resets."),

    # Overwatch 2
    _template(
        "ow2-team-wipe", "Ultimate team wipe", "ow2", "hero_shooter",
        "One ultimate, several kills. Opens on the best second, then plays the whole thing.",
        layout="gameplay_a", caption_style="pop", duration="0-30", clip_length=18, hook="excited", hook_ms=2000,
        audio=1.0, chat=0.9, bonus=0.15,
        focus="Overwatch 2 ultimates and team kills: one ultimate or a combo that kills three or more, a team "
              "wipe, a play-of-the-game moment, the kill feed filling up. Start just before the ultimate voice "
              "line and end when the last enemy drops. Skip hero select, walking back from spawn and poke with "
              "no kills."),
    _template(
        "ow2-overtime", "Overtime hold", "ow2", "hero_shooter",
        "The fight that decides the round, kept uncut so the tension builds. Camera on top for the reaction.",
        layout="split2", caption_style="boxed", duration="30-60", clip_length=40, tighten=False,
        flash_forward=False, hook="dramatic", audio=0.8, chat=1.0, bonus=0.2,
        focus="Overwatch 2 overtime: the last fight on the point or the payload, a last-second touch, a team "
              "forgetting the objective, a comeback from one tick away. Tension first, then the result: keep the "
              "fight until the victory or defeat banner and the team's reaction. Skip early-round fights that "
              "decide nothing."),

    # Minecraft
    _template(
        "minecraft-build-reveal", "Build reveal", "minecraft", "sandbox",
        "A finished build or machine shown off. The whole picture stays in frame; calm captions; hook at the end.",
        layout="fit", caption_style="clean", duration="60-90", clip_length=60, punch_zoom=False,
        hook="inspirational", hook_position="end", hook_ms=3500, audio=0.5, chat=1.0, bonus=0.25,
        focus="Minecraft builds and reveals: a finished build shown off, a before and after, a redstone machine "
              "or farm working the first time, the end of a long project. The explanation and the reaction "
              "matter; quiet footage is fine when the picture is impressive. End on the full view of the build. "
              "Skip mining, gathering, inventory sorting and travelling."),
    _template(
        "minecraft-close-call", "Close call", "minecraft", "sandbox",
        "Creepers, falls, lava and the scream. Very short, small camera in the corner.",
        layout="pip", caption_style="neon", duration="0-30", clip_length=15, hook="humorous", hook_ms=2000,
        audio=1.0, chat=0.9, bonus=0.2,
        focus="Minecraft near-deaths and deaths: a creeper behind the player, a fall, lava, the warden, a "
              "hardcore world on half a heart, a water-bucket save, losing everything in the void. Start as "
              "late as possible before the danger and keep the scream or the silence after. Skip calm building, "
              "farming and menus."),
    _template(
        "minecraft-smp-story", "Server story", "minecraft", "sandbox",
        "Multiplayer drama told whole: the betrayal, the prank, the deal. Long clips led by what is said.",
        layout="split2", caption_style="pop", duration="90-180", clip_length=60, punch_zoom=False,
        flash_forward=False, hook="conversational", hook_ms=3000, audio=0.6, chat=1.0, bonus=0.3,
        focus="Minecraft multiplayer story: betrayals, pranks, traps, trades, alliances, trials and arguments "
              "between players on a server. What is said matters more than the action. Pick a scene with a "
              "beginning and a payoff that a viewer understands without the rest of the stream: who wants what, "
              "and how it ends. Skip solo grinding."),

    # Apex Legends
    _template(
        "apex-squad-wipe", "Squad wipe", "apex", "battle_royale",
        "A full squad down in one fight, from the first shot to the last knock.",
        layout="gameplay_a", caption_style="bold", duration="0-30", clip_length=25, hook="excited", hook_ms=2000,
        audio=1.0, chat=0.8, bonus=0.15,
        focus="Apex Legends fights: wiping a full squad, a 1v3 clutch, chained knocks, cracked shields into a "
              "finisher, a third party won. Start at the first shot or the callout, end when the last enemy is "
              "down. Shouted callouts and the squad's reaction mark the peak. Skip the drop, looting, healing "
              "and running from the ring."),
    _template(
        "apex-final-ring", "Final ring", "apex", "battle_royale",
        "The end of the match kept uncut: the last ring, the last fight, the result.",
        layout="screen_first", caption_style="boxed", duration="60-90", clip_length=60, tighten=False,
        flash_forward=False, hook="dramatic", hook_ms=3000, audio=0.9, chat=0.9, bonus=0.15,
        focus="Apex Legends endgame: the last squads in the final ring. Positioning, the ring closing, the last "
              "fight, then the champion screen or the loss. Keep enough build-up that the ending lands and "
              "always include the result. Skip mid-game rotations, looting and fights that do not decide the "
              "match."),

    # Valorant
    _template(
        "valorant-clutch", "Spike clutch", "valorant", "tactical_shooter",
        "One player left. Nothing is cut or zoomed: the quiet before the shots is the clip.",
        layout="split2", caption_style="boxed", duration="30-60", clip_length=35, tighten=False, punch_zoom=False,
        flash_forward=False, hook="dramatic", audio=0.8, chat=1.0, bonus=0.2,
        focus="Valorant clutches: one player left against two or more, the spike planted or the defuse ticking. "
              "The quiet before the shots is part of the clip: keep the setup, every kill and the round result, "
              "then the team's reaction. Skip the buy phase, full five-on-five executes and rounds lost without "
              "a fight."),
    _template(
        "valorant-ace", "Ace and flicks", "valorant", "tactical_shooter",
        "Aim highlights: the ace, the flick, the wallbang. As short as the kills allow.",
        layout="gameplay_a", caption_style="pop", duration="0-30", clip_length=15, flash_forward=False,
        hook="excited", hook_ms=2000, audio=1.0, chat=0.9, bonus=0.15,
        focus="Valorant aim highlights: aces, four-kills, flick headshots, wallbangs, Operator shots, kills "
              "through smoke, a pistol beating rifles. Start just before the first kill and end on the last one "
              "or the ace announcer. Fast, mechanical moments matter more than talk. Skip the buy phase, "
              "walking and trades with no multi-kill."),
    _template(
        "valorant-ranked-comms", "Ranked comms", "valorant", "tactical_shooter",
        "Voice chat gold: the rage, the bad call, the teammate with the perfect line.",
        layout="pip", caption_style="neon", duration="0-90", clip_length=30, punch_zoom=False, hook="parody",
        audio=0.6, chat=1.0, bonus=0.3,
        focus="Valorant voice chat: funny, angry or absurd team comms in ranked. A callout that goes wrong, a "
              "teammate raging, an instalock argument, a random with a great line, the whole team laughing after "
              "a throw. What is said matters more than the round. Keep the setup line and the reply. Skip plain "
              "callouts and silence."),

    # Fortnite
    _template(
        "fortnite-build-fight", "Build fight", "fortnite", "battle_royale",
        "Box fights, edits and the finishing shot, full screen and fast.",
        layout="full", caption_style="neon", duration="0-30", clip_length=20, flash_forward=False, hook="excited",
        hook_ms=2000, audio=1.0, chat=0.8, bonus=0.1,
        focus="Fortnite fights: build battles, box fights, fast edits, taking the high ground back, a clean "
              "shotgun finish; in Zero Build, movement and cover fights. Start when the fight is joined and end "
              "on the elimination. Skip farming materials, looting, the bus and long rotations."),
    _template(
        "fortnite-endgame", "Last circle win", "fortnite", "battle_royale",
        "The final circle through the win screen, uncut, with the reaction under the gameplay.",
        layout="gameplay_b", caption_style="pop", duration="60-90", clip_length=60, tighten=False,
        hook="dramatic", hook_ms=3000, audio=0.9, chat=0.9, bonus=0.15,
        focus="Fortnite endgame: the last few players in the final circle through the win or the loss. Moving "
              "zone, low materials, the last fight, then the Victory Royale screen and the reaction. Always "
              "include the result. Skip early-game drops and mid-game fights that do not lead to the ending."),

    # Dota 2
    _template(
        "dota2-teamfight", "Wide team fight", "dota2", "moba",
        "Five-on-five fights in widescreen, from the initiation to what the fight wins. Nothing cut, nothing zoomed.",
        layout="full", aspect="16:9", caption_style="clean", duration="60-90", clip_length=60, tighten=False,
        punch_zoom=False, flash_forward=False, hook="informative", hook_ms=3000, audio=0.9, chat=0.9, bonus=0.15,
        focus="Dota 2 team fights: Roshan fights, high-ground pushes, smoke ganks that turn into five-on-fives, "
              "big ultimates landing on several heroes, buybacks, an Aegis steal, a team wipe. Keep the "
              "initiation, the fight and what it wins: the wipe, the barracks, the throne. Skip laning, "
              "farming, shopping and the draft."),
    _template(
        "dota2-rampage", "Rampage play", "dota2", "moba",
        "One hero taking over: the rampage, the juke, the escape on one hit point.",
        layout="gameplay_b", caption_style="bold", duration="0-30", clip_length=22, hook="excited", hook_ms=2000,
        audio=1.0, chat=0.9, bonus=0.15,
        focus="Dota 2 solo plays: a rampage or ultra kill, an escape on one hit point, a juke through the trees, "
              "a blink or immunity pressed at the last instant, a carry turning a fight alone, a courier snipe. "
              "Start just before the play and end on the kill streak banner or the escape. Skip farming and "
              "fights with no single standout hero."),

    # Rust
    _template(
        "rust-raid", "Raid night", "rust", "survival",
        "A raid from the first rocket to the loot room, with the waiting cut out.",
        layout="screen_first", caption_style="boxed", duration="90-180", clip_length=60, punch_zoom=False,
        hook="serious", hook_ms=3000, audio=1.0, chat=0.8, bonus=0.15,
        focus="Rust raids: rockets and explosives going off, walls breached, defenders fighting back, a "
              "counter-raid, the loot room opened or the raid failing. Keep the breach, the fight inside and the "
              "result: what was won or lost. Skip farming, crafting, building and long waits between rockets."),
    _template(
        "rust-voice-chat", "Door talk", "rust", "survival",
        "Strangers on voice chat: the deal, the betrayal, the trash talk. Camera on top, led by what is said.",
        layout="split2", caption_style="pop", duration="30-60", clip_length=40, punch_zoom=False,
        flash_forward=False, hook="casual", audio=0.6, chat=1.0, bonus=0.3,
        focus="Rust voice-chat encounters: strangers talking at a door, a deal, a betrayal, a fresh spawn "
              "talking their way out, a neighbour feud, trash talk after a kill. What is said matters more than "
              "the gunfight. Keep the first line, the turn and how it ends. Skip silent roaming, farming and "
              "base building."),

    # Counter-Strike 2
    _template(
        "cs2-clutch", "Bomb site clutch", "cs2", "tactical_shooter",
        "Last player alive with the bomb down. Uncut, small camera in the corner, quiet captions.",
        layout="pip", caption_style="clean", duration="30-60", clip_length=30, tighten=False, punch_zoom=False,
        flash_forward=False, hook="serious", audio=0.8, chat=1.0, bonus=0.2,
        focus="Counter-Strike 2 clutches: last player alive against two or more, the bomb planted, a defuse "
              "with no time left, a fake defuse, a silent knife. Footsteps and silence build the tension: keep "
              "the setup, each kill and the round result, then the team's reaction. Skip the buy time, freeze "
              "time and rounds decided five against five."),
    _template(
        "cs2-frag-highlight", "Frag highlight", "cs2", "tactical_shooter",
        "Pure aim: the ace, the flick, the no-scope. The shortest clips in the catalogue.",
        layout="full", caption_style="bold", duration="0-30", clip_length=12, flash_forward=False, hook="excited",
        hook_ms=1500, audio=1.0, chat=0.8, bonus=0.1,
        focus="Counter-Strike 2 frags: aces, AWP flicks, no-scopes, wallbangs, spray transfers across several "
              "enemies, pistol headshots on a save round, a knife kill. Start just before the first shot, end "
              "on the last kill. Pure aim moments: the play matters more than the talk. Skip buy time, utility "
              "setup and single trade kills."),

    # Any other game
    _template(
        "any-game-highlights", "Any game highlights", "other", "variety",
        "For any game: the loud, surprising moments and the reaction to them.",
        layout="auto", caption_style="bold", duration="0-90", clip_length=30, hook="casual",
        audio=0.7, chat=1.0, bonus=0.15,
        focus="Gameplay highlights from any game: wins, kills, fails, close calls, surprises and the streamer's "
              "loud reaction to them. Pick moments a viewer understands without knowing the stream: something "
              "happens, and it has an ending. Skip menus, loading screens, queues, tutorials and long stretches "
              "where nothing changes."),
    _template(
        "stream-talk", "Stream talk", "other", "variety",
        "Talk between games: the story, the opinion, the argument. Camera on top, hook at the end.",
        layout="split2", caption_style="clean", duration="30-60", clip_length=45, punch_zoom=False,
        flash_forward=False, hook="persuasive", hook_position="end", hook_ms=3000, audio=0.6, chat=1.0, bonus=0.3,
        focus="Talk between games: a story with an ending, a strong opinion, an argument, a joke, an answer to "
              "chat, a reaction to a video or a donation. What is said is the whole clip: it needs a complete "
              "thought and a payoff, and must make sense alone. Skip greetings, reading out names, technical "
              "problems and silence."),
]

TEMPLATES: dict[str, dict] = {t["id"]: t for t in _CATALOGUE}


def problems(template_id: str, t: dict) -> list[str]:
    """Everything wrong with one template, as plain sentences. Empty when it follows the format."""
    hook, options, bad = t.get("hook") or {}, t.get("options") or {}, []
    lo, hi = DURATIONS.get(t.get("duration"), (0, 0))
    length = options.get("clip_length", 0)
    checks = [
        (t.get("id") == template_id, "id does not match its key"),
        (bool(t.get("name")) and len(t.get("name", "")) <= 28, "name is missing or over 28 characters"),
        (bool(t.get("description")), "description is missing"),
        (t.get("game") in GAMES, "unknown game"),
        (t.get("genre") in GENRES, "unknown genre"),
        (t.get("layout") in LAYOUTS, "unknown layout"),
        (t.get("aspect") in ASPECTS, "unknown aspect"),
        (t.get("caption_style") in CAPTION_STYLES, "unknown caption_style"),
        (t.get("duration") in DURATIONS, "unknown duration bucket"),
        (set(hook) == {"enabled", "style", "position", "duration_ms"}, "hook needs enabled, style, position, duration_ms"),
        (isinstance(hook.get("enabled"), bool), "hook.enabled is not true or false"),
        (hook.get("style") in HOOK_STYLES, "unknown hook style"),
        (hook.get("position") in HOOK_POSITIONS, "unknown hook position"),
        (isinstance(hook.get("duration_ms"), int) and 1000 <= hook.get("duration_ms", 0) <= 6000, "hook.duration_ms is outside 1000-6000"),
        (options.get("layout") == TODAY_LAYOUT.get(t.get("layout")), "options.layout disagrees with layout"),
        (options.get("caption_style") == t.get("caption_style"), "options.caption_style disagrees with caption_style"),
        (options.get("hook_overlay") == hook.get("enabled"), "options.hook_overlay disagrees with hook.enabled"),
        (options.get("aspect", "9:16") == t.get("aspect"), "options.aspect disagrees with aspect"),
        # The clip length sits inside the bucket, or is today's longest when the bucket starts above it.
        (max(lo, 10) <= length <= hi or (lo >= MAX_CLIP_LENGTH and length == MAX_CLIP_LENGTH),
         "options.clip_length is outside the duration bucket"),
        (not set(options) & set(TUNING_FIELDS), "tuning inside options"),
        (set(t.get("weights") or {}) == {"audio", "chat_motion"}
         and all(0 < v <= 1.5 for v in (t.get("weights") or {}).values()), "weights must be audio and chat_motion, 0-1.5"),
        (0 <= t.get("transcript_bonus", -1) <= 0.3, "transcript_bonus is outside 0-0.3"),
        (40 < len(t.get("judge_focus") or "") <= JUDGE_FOCUS_MAX, f"judge_focus must be 41-{JUDGE_FOCUS_MAX} characters"),
        (set(t.get("preview") or {}) == {"video", "poster"}, "preview needs video and poster"),
    ]
    return [f"{template_id}: {message}" for ok, message in checks if not ok]


# A bad entry stops the API at start-up, not at the first request that reads it.
_problems = [p for tid, t in TEMPLATES.items() for p in problems(tid, t)]
if len(TEMPLATES) != len(_CATALOGUE):
    _problems.append("two templates share an id")
if _problems:
    raise ValueError("bad template catalogue: " + "; ".join(_problems))


def public(template_id: str) -> dict:
    """What the public list shows: everything except the detection tuning."""
    t = TEMPLATES[template_id]
    return {k: t[k] for k in PUBLIC_FIELDS}


def for_game(game: str | None = None) -> list[dict]:
    """Public templates in catalogue order (grouped by game, in GAMES order). `game` narrows to one game."""
    return [public(tid) for tid, t in TEMPLATES.items() if game is None or t["game"] == game]


def games() -> list[dict]:
    """Every game with its display name and how many templates it has, in GAMES order."""
    return [{"id": g, "name": GAME_NAMES[g], "templates": sum(t["game"] == g for t in TEMPLATES.values())} for g in GAMES]


def with_tuning(options: dict) -> dict:
    """`options` plus its template's detection tuning (weights, transcript bonus, judge focus). The options
    themselves are never changed here: a client applies a template's `options` by sending them, so what a job
    renders, and therefore what it costs, is always exactly what the request says. No template: unchanged."""
    template = TEMPLATES.get(options.get("template") or "")
    if not template:
        return options
    return {**options, "weights": template["weights"], "transcript_bonus": template["transcript_bonus"],
            "judge_focus": template["judge_focus"]}
