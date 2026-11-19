// The caption fonts the renderer ships (#213, app/fonts: Anton, Bebas Neue, Bangers, Luckiest Guy, Poppins; all open
// licence) and the one-colour Noto Emoji it draws emoji with (#215), so the editor's preview uses the same faces as
// the render. Self-hosted by next/font: the files ship with the site, nothing is fetched from Google at run time.
import { Anton, Bangers, Bebas_Neue, Luckiest_Guy, Noto_Emoji, Poppins } from "next/font/google";

const anton = Anton({ weight: "400", subsets: ["latin"], display: "swap" });
const bebas = Bebas_Neue({ weight: "400", subsets: ["latin"], display: "swap" });
const bangers = Bangers({ weight: "400", subsets: ["latin"], display: "swap" });
const luckiest = Luckiest_Guy({ weight: "400", subsets: ["latin"], display: "swap" });
const poppins = Poppins({ weight: ["400", "700", "900"], style: ["normal", "italic"], subsets: ["latin"], display: "swap" });
const emoji = Noto_Emoji({ subsets: ["emoji"], display: "swap" });

// API font id to CSS family. A font id this site doesn't know (an account's own "custom:<id>") has no family here.
export const CAPTION_FONTS: Record<string, { name: string; family: string; weights: string[] }> = {
  anton: { name: "Anton", family: anton.style.fontFamily, weights: ["regular"] },
  bebas: { name: "Bebas Neue", family: bebas.style.fontFamily, weights: ["regular"] },
  bangers: { name: "Bangers", family: bangers.style.fontFamily, weights: ["regular"] },
  luckiest: { name: "Luckiest Guy", family: luckiest.style.fontFamily, weights: ["regular"] },
  poppins: { name: "Poppins", family: poppins.style.fontFamily, weights: ["regular", "bold", "black"] },
};
export const EMOJI_FAMILY = emoji.style.fontFamily;
// The renderer's default face for impact captions when no font is chosen.
export const DEFAULT_FONT = "anton";
export const WEIGHT_CSS: Record<string, number> = { regular: 400, bold: 700, black: 900 };
