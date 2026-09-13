import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TimeOS",
  description: "Personal Time Intelligence System",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="bg-neutral-50 text-neutral-900 antialiased">{children}</body>
    </html>
  );
}
