import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Privacy · nightly" };

const REPO = "https://github.com/Suharshit/nightly";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="font-display text-lg font-medium">{title}</h2>
      <div className="flex flex-col gap-2 text-sm leading-relaxed text-muted">{children}</div>
    </section>
  );
}

/** Plain-language privacy policy. Keep it in step with what the code actually stores. */
export default function Privacy() {
  return (
    <article className="page gap-6 pb-10">
      <header>
        <h1 className="font-display text-2xl font-medium tracking-tight">Privacy policy</h1>
        <p className="mt-1 text-sm text-muted">Last updated 28 November 2026 (bug reports added)</p>
      </header>

      <p className="text-sm leading-relaxed text-muted">
        nightly is a free student project that matches startup jobs to your resume. This page says
        what we collect, why, and who else handles it. We do not sell your data or show ads.
      </p>

      <Section title="What we collect">
        <ul className="list-disc space-y-1 pl-5">
          <li><span className="text-text">Account:</span> your email address. If you sign in with
            Google, Google also shares your name and profile picture, which our sign-in provider
            stores with your account.</li>
          <li><span className="text-text">Resume:</span> the text we read from the PDF you upload,
            the skills we find in it, and a numeric summary (an embedding) used for matching. We
            do not keep the PDF file itself.</li>
          <li><span className="text-text">Preferences:</span> the roles, cities and experience level
            you choose, and anything you ask the chat to remember.</li>
          <li><span className="text-text">Activity:</span> which jobs we showed you, and which you
            liked, disliked, opened or shared, with any reason you gave.</li>
          <li><span className="text-text">Chat:</span> your messages and the replies, plus timing and
            error logs for each reply.</li>
          <li><span className="text-text">Bug reports:</span> what you write on the Report a bug
            page, where it happened, your screen size and browser name, and an email only if you
            give one. Delete my data removes the email and the link to your account.</li>
          <li><span className="text-text">On your device:</span> your theme choice and the link you
            arrived from (for example a WhatsApp share), kept in your browser&apos;s local storage.</li>
        </ul>
      </Section>

      <Section title="How we use it">
        <p>Only to run nightly: to sign you in, rank jobs for you, explain why a job fits, remember
          your preferences, and measure whether the matching and chat work well. We count usage
          (for example sign-ups by where people came from) in aggregate.</p>
      </Section>

      <Section title="Who else handles it">
        <ul className="list-disc space-y-1 pl-5">
          <li><span className="text-text">Supabase</span> stores your account and the data above
            (servers in Singapore).</li>
          <li><span className="text-text">Vercel</span> serves this website, and our API runs on
            <span className="text-text"> Hugging Face</span> Spaces. The matching models run on our
            own server, so your resume text is not sent to an AI provider.</li>
          <li><span className="text-text">Groq</span> runs the open-weight model behind the chat. It
            receives your chat messages, a short profile summary (skills and preferences), and the
            job details the chat looks up.</li>
          <li><span className="text-text">Google</span>, only if you choose to sign in with it.</li>
        </ul>
        <p>Job listings come from companies&apos; public job boards (Greenhouse, Lever and Ashby).
          We never share your data with the companies whose jobs we show.</p>
      </Section>

      <Section title="Your choices">
        <p>You can change your preferences at any time. To delete your account and everything
          linked to it, open the <span className="text-text">•••</span> menu and tap{" "}
          <span className="text-text">Delete my data</span>. It removes your account, resume, preferences, activity, chat
          history and chat logs straight away.</p>
        <p>For a copy of your data, open an issue on our{" "}
          <a href={`${REPO}/issues`} className="text-text underline">GitHub page</a> and we will
          reply there with how to confirm it is you.</p>
      </Section>

      <Section title="Changes">
        <p>If this policy changes, we will update the date at the top of this page.</p>
      </Section>

      <Link href="/" className="text-sm text-muted underline">Back to nightly</Link>
    </article>
  );
}
