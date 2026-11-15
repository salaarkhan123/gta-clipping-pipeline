import "@fontsource-variable/archivo/standard.css";
import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "ClutchClips: turn stream recordings into ready-to-post clips",
  description: "Upload a gameplay recording. ClutchClips finds the best moments, stacks your camera over the gameplay, adds captions and gives you clips for TikTok, Shorts and Reels.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (<html lang="en"><body>{children}</body></html>);
}
