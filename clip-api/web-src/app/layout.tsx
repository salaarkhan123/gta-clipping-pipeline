import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import "@fontsource-variable/inter";
import "./styles.css";
import type { Metadata } from "next";
import { linkPhrase } from "@/lib/platforms";

export const metadata: Metadata = {
  title: "ClutchClips: AI clipping for gaming streams",
  description: `Upload a stream recording or paste ${linkPhrase()}. ClutchClips finds the best moments, stacks your facecam over the gameplay, adds animated captions, and gives every clip an AI rating.`,
};

// Geist and Geist Mono are self-hosted by next/font, Inter (the app's typeface) by @fontsource: all SIL Open Font
// License, and the files ship with the site.
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (<html lang="en" className={`${GeistSans.variable} ${GeistMono.variable}`}><body>{children}</body></html>);
}
