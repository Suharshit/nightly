"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { Level } from "@/lib/types";
import { useSession } from "@/lib/useSession";

const ROLES = ["Backend", "Frontend", "Full-stack", "Data", "ML / AI", "DevOps", "Mobile", "Design"];
const CITIES = ["Bengaluru", "Hyderabad", "Pune", "Mumbai", "Chennai", "Gurugram", "Noida"];
const LEVELS: { value: Level; label: string }[] = [
  { value: "student", label: "Student (internships)" },
  { value: "fresher", label: "Fresher (0–1 yrs)" },
  { value: "junior", label: "1–2 yrs" },
];

function Chip({ on, children, onClick }: { on: boolean; children: React.ReactNode; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} aria-pressed={on}
            className={`btn px-3 py-1.5 ${on ? "btn-primary" : ""}`}>
      {children}
    </button>
  );
}

function toggle(list: string[], v: string) {
  return list.includes(v) ? list.filter((x) => x !== v) : [...list, v];
}

/** Under 60 s: resume PDF, then role, location and experience chips. */
export default function Onboard() {
  const router = useRouter();
  const session = useSession();
  const [file, setFile] = useState<File | null>(null);
  const [skills, setSkills] = useState<string[] | null>(null);
  const [roles, setRoles] = useState<string[]>([]);
  const [cities, setCities] = useState<string[]>([]);
  const [remote, setRemote] = useState(false);
  const [level, setLevel] = useState<Level | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Editing later: start from the saved resume and preferences instead of a blank form.
  useEffect(() => {
    if (!session) return;
    api.me().then((me) => {
      if (me.has_resume) setSkills(me.resume_skills);
      setRoles(me.prefs.roles ?? []);
      setCities(me.prefs.cities ?? []);
      setRemote(!!me.prefs.remote);
      if (me.prefs.level) setLevel(me.prefs.level as Level);
    }, () => {});
  }, [session]);

  async function upload(f: File) {
    setFile(f);
    setError(null);
    setBusy(true);
    try {
      setSkills((await api.uploadResume(f)).skills);
    } catch (e) {
      setFile(null);
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function finish() {
    setBusy(true);
    setError(null);
    try {
      // Where this user came from (?ref=...), saved on the landing page, for signup stats.
      const saved = (localStorage.getItem("ref") || "").toLowerCase();
      const ref = /^[a-z0-9_-]{1,32}$/.test(saved) ? saved : undefined;
      await api.setPrefs({ roles, cities, remote, level: level ?? undefined, ref });
      router.push("/feed");
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  if (session === undefined) return null;
  const ready = skills !== null && level !== null && (cities.length > 0 || remote);

  return (
    <div className="page gap-7">
      <h1 className="font-display text-2xl font-medium">Set up your matches</h1>

      <section>
        <h2 className="mb-2 text-sm font-medium">1. Your resume (PDF)</h2>
        <label className="box flex cursor-pointer items-center justify-between border-dashed px-4 py-4">
          <span className="truncate text-sm">
            {busy && file && !skills ? "Reading your resume…" : file ? file.name : skills ? "Resume on file" : "Choose a PDF"}
          </span>
          <span className="text-sm text-accent">{skills ? "Change" : "Upload"}</span>
          <input type="file" accept="application/pdf" className="hidden"
                 onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
        </label>
        {skills && (
          <p className="mt-2 text-sm text-muted">
            {skills.length ? `Found: ${skills.slice(0, 8).join(", ")}` : "Read it, but found no skills we know yet."}
          </p>
        )}
        <p className="mt-2 text-xs text-muted">
          We keep only your resume&apos;s text, to match you with jobs, and never share it.
          Delete it any time from the ••• menu. <Link href="/privacy" className="underline">Privacy</Link>
        </p>
      </section>

      <section>
        <h2 className="mb-2 text-sm font-medium">2. What kind of role?</h2>
        <div className="flex flex-wrap gap-2">
          {ROLES.map((r) => <Chip key={r} on={roles.includes(r)} onClick={() => setRoles(toggle(roles, r))}>{r}</Chip>)}
        </div>
      </section>

      <section>
        <h2 className="mb-2 text-sm font-medium">3. Where?</h2>
        <div className="flex flex-wrap gap-2">
          <Chip on={remote} onClick={() => setRemote(!remote)}>Remote</Chip>
          {CITIES.map((c) => <Chip key={c} on={cities.includes(c)} onClick={() => setCities(toggle(cities, c))}>{c}</Chip>)}
        </div>
      </section>

      <section>
        <h2 className="mb-2 text-sm font-medium">4. Experience</h2>
        <div className="flex flex-wrap gap-2">
          {LEVELS.map((l) => <Chip key={l.value} on={level === l.value} onClick={() => setLevel(l.value)}>{l.label}</Chip>)}
        </div>
      </section>

      {error && <p className="text-sm text-muted">{error}</p>}
      <button onClick={finish} disabled={!ready || busy}
              className="btn btn-primary py-3">
        {busy && skills ? "Saving…" : "Show my matches"}
      </button>
    </div>
  );
}
