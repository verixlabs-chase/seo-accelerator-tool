import "./globals.css";

export const metadata = {
  title: "InsightOS",
  description: "Your local search command center"
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
