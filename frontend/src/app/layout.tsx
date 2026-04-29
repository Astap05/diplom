import type { Metadata } from "next";
import "./globals.css";
import "vis-timeline/styles/vis-timeline-graph2d.min.css";

export const metadata: Metadata = {
  title: "Airport RMS — Диспетчерский дашборд",
  description: "Распределение ресурсов аэропорта: стойки регистрации и выходы на посадку",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ru" className="dark">
      <head />
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
