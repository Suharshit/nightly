/** @type {import('next').NextConfig} */

// Where the browser may connect: our API and Supabase (sign-in). Read at build time.
const origin = (url) => {
  try { return url ? new URL(url).origin : ""; } catch { return ""; }
};
const connect = ["'self'", origin(process.env.NEXT_PUBLIC_API_URL),
                 origin(process.env.NEXT_PUBLIC_SUPABASE_URL)].filter(Boolean).join(" ");

// Next.js and the theme script use small inline scripts, so script-src needs 'unsafe-inline';
// everything else is locked to this site. Production only: the dev server needs eval.
const csp = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self'",
  `connect-src ${connect}`,
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const securityHeaders = [
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
  ...(process.env.NODE_ENV === "production" ? [{ key: "Content-Security-Policy", value: csp }] : []),
];

const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};
export default nextConfig;
