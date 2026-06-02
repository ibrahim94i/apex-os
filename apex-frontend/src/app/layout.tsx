import type { Metadata } from "next";
import "./globals.css";
import NotificationInitializer from "@/components/NotificationInitializer";

export const metadata: Metadata = {
  title: "APEX — لوحة التداول",
  description: "لوحة معلومات التداول الذكية",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ar" dir="rtl">
      <body>
        <NotificationInitializer />
        {children}
      </body>
    </html>
  );
}
