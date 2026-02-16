import "./globals.css";

export const metadata = {
  title: "LSOS Portal",
  description: "Tenant-aware SEO operations portal"
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
