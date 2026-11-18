import "@fontsource/poppins/600.css";
import "@fontsource/poppins/700.css";
import "@fontsource/poppins/800.css";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "./globals.css";
import "./app-shell.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "ClutchClips: AI clipping for gaming streams",
  description: "Upload a stream recording. ClutchClips finds the best moments, stacks your facecam over the gameplay, adds animated captions, and scores every clip.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (<html lang="en"><body>{children}</body></html>);
}
