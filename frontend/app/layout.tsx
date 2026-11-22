import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Compliance OS — Readiness & evidence automation for Moroccan exporters",
  description:
    "ISO 27001, SOC 2 and Morocco's Loi 09-08 / Loi 05-20 readiness in one evidence programme, with a grounded compliance agent.",
  metadataBase: new URL("https://www.complianceos.ma"),
  openGraph: {
    title: "Compliance OS",
    description:
      "Answer the next security questionnaire in days, not weeks. ISO 27001, SOC 2 and the Moroccan regulatory layer, in one evidence programme.",
    type: "website",
  },
};

export const viewport: Viewport = {
  themeColor: "#08090d",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
