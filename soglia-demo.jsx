import React, { useState, useEffect, useRef, useMemo } from "react";
import * as XLSX from "xlsx";
import {
  Upload, FileSpreadsheet, FileText, ArrowRight, Check, AlertTriangle,
  CircleAlert, X, MapPin, ShieldCheck, Clock, MousePointerClick, RotateCcw,
  Info, Download, Table2, Wand2, ChevronRight, CornerDownRight, FileCheck2,
} from "lucide-react";

/* ────────────────────────────────────────────────────────────────────────
   Soglia — rooming-list normalizer demo
   The boundary where the list they sent becomes the file the desk needs.
   Sample data only. Codes are illustrative; production uses the official
   Questura reference tables.
   ──────────────────────────────────────────────────────────────────────── */

const FONT_CSS = `
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');
.sg-sans{font-family:'IBM Plex Sans',ui-sans-serif,system-ui,-apple-system,sans-serif;}
.sg-mono{font-family:'IBM Plex Mono',ui-monospace,'SF Mono',Menlo,monospace;font-variant-ligatures:none;}
@keyframes sg-fade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.sg-fade{animation:sg-fade .45s ease both;}
@keyframes sg-pulse{0%,100%{opacity:1}50%{opacity:.45}}
.sg-pulse{animation:sg-pulse 1.1s ease-in-out infinite;}
@media (prefers-reduced-motion: reduce){.sg-fade,.sg-pulse{animation:none!important}}
`;

/* ── The list as it arrived: a real, messy worker-crew sheet ──────────────
   Romanian construction crew. No sex column. No citizenship column (it's an
   annotation up top). An issue-date column that mustn't be read as a birth
   date. A totals row to skip. One impossible date. One ambiguous birthplace. */

const RAW = {
  title: "CANTIERE MILANO EST — SQUADRA GIUGNO 2026",
  annotation: "Cittadinanza: ROMANIA",
  headers: ["Cognome", "Nome", "Data di nascita", "Luogo di nascita", "Documento", "Rilasciato il", "Camera"],
  // each: surname, name, dob, birthplace, doc, issued, room
  rows: [
    { r: 4,  cells: ["POPESCU",    "Ion",      "14/03/1979", "Bucuresti",   "C.I. RO5582013", "12/04/2019", "101"] },
    { r: 5,  cells: ["IONESCU",    "Maria",    "22/07/1985", "Cluj-Napoca", "", "", "101"] },
    { r: 6,  cells: ["DUMITRU",    "Gheorhe",  "05/11/1990", "Iasi",        "", "", "102"] },
    { r: 7,  cells: ["CONSTANTIN", "Elena",    "30/02/1992", "Constanta",   "", "", "102"] },
    { r: 8,  cells: ["GEORGESCU",  "Andrei",   "18/09/1988", "Monaco",      "", "", "103"] },
    { r: 9,  cells: ["STAN",       "Cristina", "12/01/1995", "Timisoara",   "", "", "103"] },
    { r: 10, cells: ["MARIN",      "Vasile",   "03/05/1981", "Bucuresti",   "", "", "104"] },
    { r: 11, cells: ["RADU",       "Florin",   "27/12/1983", "Brasov",      "", "", "104"] },
  ],
  totalsRow: 12,
};
const COLS = ["A", "B", "C", "D", "E", "F", "G"];

/* ── The canonical model the LLM hands off (transcription, not interpretation).
   Each field: resolved value, the verbatim string + where it came from,
   a derived tier, and an origin. Reds block approval; yellows are one click. */

function buildGuests() {
  const sexByName = { Ion: "M", Maria: "F", Gheorhe: "M", Elena: "F", Andrei: "M", Cristina: "F", Vasile: "M", Florin: "M" };
  return RAW.rows.map((row, i) => {
    const [surname, name, dob, place, doc] = row.cells;
    const r = row.r;
    const head = i === 0;
    const f = {};

    f.cognome = { value: surname, verbatim: surname, source: `A${r}`, tier: "green", origin: "extracted",
      reason: "Found at the named cell, agreed across two reads, passes every check." };

    f.nome = { value: name, verbatim: name, source: `B${r}`, tier: "green", origin: "extracted",
      reason: "Found at the named cell, agreed across two reads." };

    f.sesso = { value: sexByName[name], verbatim: null, source: "inferred", tier: "yellow", origin: "inferred",
      reason: "Inferred from the first name — the file has no sex column. The police format requires it." };

    f.nascita = { value: dob, verbatim: dob, source: `C${r}`, tier: "green", origin: "extracted",
      reason: "Found at the named cell; parses as a real date in range." };

    f.luogo = { value: place, verbatim: place, source: `D${r}`, tier: "green", origin: "extracted",
      reason: "Resolved to a single place — born abroad, so the birth-comune fields stay blank.", resolved: "Romania" };

    f.cittadinanza = { value: "Romania", verbatim: "ROMANIA", source: "annotation A2", tier: "yellow", origin: "inferred",
      reason: "Filled down from “Cittadinanza: ROMANIA” at the top of the sheet — not a per-guest column." };

    f.documento = head
      ? { value: "Carta d'identità · RO5582013", verbatim: doc, source: `E${r}`, tier: "green", origin: "extracted",
          reason: "Group head — document fields are required and were present in the file." }
      : { value: null, verbatim: null, source: null, tier: "green", origin: "extracted",
          reason: "Group member — the police format wants these fields empty. Correct." };

    f.room = { value: row.cells[6], verbatim: row.cells[6], source: `G${r}`, tier: "green", origin: "extracted",
      reason: "Not required by the police portal; carried through for your records." };

    // The two genuine red blockers and the one name to verify.
    if (name === "Elena") {
      f.nascita = { ...f.nascita, tier: "red",
        reason: "30 February isn’t a real date — a typo in the original. Check it against the guest’s ID.", needsDate: true };
    }
    if (name === "Andrei") {
      f.luogo = { ...f.luogo, tier: "red", resolved: null,
        reason: "“Monaco” is ambiguous — in Italian it’s usually Munich, but it could be the principality. The tool won’t guess.",
        candidates: ["München, Germania", "Principato di Monaco"] };
    }
    if (name === "Gheorhe") {
      f.nome = { ...f.nome, tier: "yellow",
        reason: "Unusual spelling — likely a typo for “Gheorghe.” The tool never auto-corrects names; reported as written, verify at check-in." };
    }

    return { id: i, role: head ? "Capo gruppo" : "Membro gruppo", roleCode: head ? "18" : "20", room: row.cells[6], name, f };
  });
}

/* ── Alloggiati Web "tracciato record": 168 fixed-width chars, one per guest.
   This is the artifact the whole pipeline exists to produce, byte-exact. ── */

const TR_FIELDS = [
  { k: "tipo",    label: "Tipo",        len: 2 },
  { k: "arrivo",  label: "Arrivo",      len: 10 },
  { k: "giorni",  label: "Notti",       len: 2 },
  { k: "cognome", label: "Cognome",     len: 50 },
  { k: "nome",    label: "Nome",        len: 30 },
  { k: "sesso",   label: "Sesso",       len: 1 },
  { k: "nascita", label: "Nascita",     len: 10 },
  { k: "comune",  label: "Comune nasc.",len: 9 },
  { k: "prov",    label: "Prov.",       len: 2 },
  { k: "stato",   label: "Stato nasc.", len: 9 },
  { k: "citt",    label: "Cittad.",     len: 9 },
  { k: "tdoc",    label: "Tipo doc",    len: 5 },
  { k: "ndoc",    label: "Num. doc",    len: 20 },
  { k: "ril",     label: "Luogo ril.",  len: 9 },
];
const SEG_TINT = [
  "bg-slate-100 text-slate-700", "bg-sky-100 text-sky-800", "bg-teal-100 text-teal-800",
  "bg-indigo-100 text-indigo-800", "bg-violet-100 text-violet-800", "bg-cyan-100 text-cyan-800",
];
const STATE_CODE = { Romania: "100000100", "München, Germania": "100000122" };
const ARRIVO = "20/06/2026", GIORNI = "07";

const padR = (s, n) => (String(s ?? "") + " ".repeat(n)).slice(0, n);

function trSegments(g) {
  const sex = g.f.sesso.value === "F" ? "2" : "1";
  const statoNasc = g.f.luogo.resolved === "München, Germania" ? STATE_CODE["München, Germania"] : STATE_CODE.Romania;
  const head = g.roleCode === "18";
  return {
    tipo: padR(g.roleCode, 2),
    arrivo: padR(ARRIVO, 10),
    giorni: padR(GIORNI, 2),
    cognome: padR(g.f.cognome.value, 50),
    nome: padR(g.f.nome.value, 30),
    sesso: padR(sex, 1),
    nascita: padR(g.f.nascita.value, 10),
    comune: padR("", 9),          // born abroad → blank
    prov: padR("", 2),            // born abroad → blank
    stato: padR(statoNasc, 9),
    citt: padR(STATE_CODE.Romania, 9),
    tdoc: padR(head ? "IDENT" : "", 5),
    ndoc: padR(head ? "RO5582013" : "", 20),
    ril: padR(head ? STATE_CODE.Romania : "", 9),
  };
}
const trLine = (g) => TR_FIELDS.map((fl) => trSegments(g)[fl.k]).join("");

/* ── small ui helpers ──────────────────────────────────────────────────── */

const TIER = {
  green:  { cell: "bg-emerald-50 border-emerald-200 text-emerald-950 hover:border-emerald-400", dot: "bg-emerald-500", chip: "bg-emerald-100 text-emerald-800 border-emerald-200", label: "Verified" },
  yellow: { cell: "bg-amber-50 border-amber-300 text-amber-950 hover:border-amber-500",         dot: "bg-amber-500",   chip: "bg-amber-100 text-amber-900 border-amber-300",  label: "Check" },
  red:    { cell: "bg-red-50 border-red-300 text-red-950 hover:border-red-500",                 dot: "bg-red-500",     chip: "bg-red-100 text-red-800 border-red-300",        label: "Blocks" },
};
const fmtClock = (ms) => {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
};

function Stepper({ step }) {
  const steps = ["Intake", "Confirm columns", "Review guests", "Files"];
  const idx = ["intake", "map", "review", "files"].indexOf(step);
  return (
    <div className="flex items-center gap-1.5 sm:gap-2">
      {steps.map((s, i) => (
        <div key={s} className="flex items-center gap-1.5 sm:gap-2">
          <div className={`flex items-center gap-1.5 px-2 sm:px-2.5 py-1 rounded-full border text-[11px] sm:text-xs sg-mono tracking-tight transition-colors ${i === idx ? "border-slate-900 bg-slate-900 text-white" : i < idx ? "border-slate-300 bg-white text-slate-500" : "border-slate-200 bg-white text-slate-300"}`}>
            <span className={`grid place-items-center w-4 h-4 rounded-full text-[10px] ${i < idx ? "bg-slate-200 text-slate-600" : i === idx ? "bg-white/20" : ""}`}>{i < idx ? <Check size={11} strokeWidth={3} /> : i + 1}</span>
            <span className="hidden sm:inline">{s}</span>
          </div>
          {i < steps.length - 1 && <ChevronRight size={13} className="text-slate-300" />}
        </div>
      ))}
    </div>
  );
}

/* ════════════════════════════════════════════════════════════════════════ */

export default function Soglia() {
  const [step, setStep] = useState("intake");
  const [processing, setProcessing] = useState(false);
  const [guests, setGuests] = useState(buildGuests);
  const [sel, setSel] = useState(null); // {gid, key}
  const [startTime, setStartTime] = useState(null);
  const [now, setNow] = useState(Date.now());
  const [frozen, setFrozen] = useState(null);
  const [edits, setEdits] = useState(0);

  useEffect(() => {
    if (!startTime || step === "files") return;
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, [startTime, step]);

  const elapsed = frozen != null ? frozen : startTime ? now - startTime : 0;

  // tier tallies
  const tally = useMemo(() => {
    let g = 0, y = 0, r = 0;
    const keys = ["cognome", "nome", "sesso", "nascita", "luogo", "cittadinanza", "documento"];
    guests.forEach((gu) => keys.forEach((k) => {
      const fld = gu.f[k];
      if (k === "documento" && fld.value == null) return; // members' empty doc fields aren't gradable
      if (fld.tier === "green") g++; else if (fld.tier === "yellow") y++; else r++;
    }));
    return { g, y, r };
  }, [guests]);

  const sourceRef = sel ? guests[sel.gid].f[sel.key].source : null;

  /* mutations */
  const bump = () => setEdits((e) => e + 1);
  const patch = (gid, key, next) => setGuests((gs) => gs.map((g, i) => i === gid ? { ...g, f: { ...g.f, [key]: { ...g.f[key], ...next } } } : g));

  const confirmField = (gid, key) => { patch(gid, key, { tier: "green", origin: "manual" }); bump(); };
  const editField = (gid, key, value, resolved) => { patch(gid, key, { value, tier: "green", origin: "manual", resolved: resolved ?? null, candidates: undefined, needsDate: false }); bump(); };
  const bulkSex = () => { setGuests((gs) => gs.map((g) => g.f.sesso.tier === "green" ? g : { ...g, f: { ...g.f, sesso: { ...g.f.sesso, tier: "green", origin: "manual" } } })); bump(); };
  const bulkCit = () => { setGuests((gs) => gs.map((g) => g.f.cittadinanza.tier === "green" ? g : { ...g, f: { ...g.f, cittadinanza: { ...g.f.cittadinanza, tier: "green", origin: "manual" } } })); bump(); };

  const startProcess = () => {
    setProcessing(true);
    setStartTime(Date.now());
    setTimeout(() => { setProcessing(false); setStep("map"); }, 1500);
  };
  const approve = () => { setFrozen(now - startTime); setStep("files"); };
  const reset = () => { setGuests(buildGuests()); setStep("intake"); setSel(null); setStartTime(null); setFrozen(null); setEdits(0); setProcessing(false); };

  return (
    <div className="sg-sans min-h-screen bg-stone-100 text-slate-900">
      <style>{FONT_CSS}</style>

      {/* top bar */}
      <header className="sticky top-0 z-30 bg-stone-100/90 backdrop-blur border-b border-stone-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="grid place-items-center w-8 h-8 rounded-lg bg-slate-900 text-white shrink-0">
              <CornerDownRight size={17} strokeWidth={2.4} />
            </div>
            <div className="min-w-0">
              <div className="font-bold tracking-tight leading-none">Soglia</div>
              <div className="text-[11px] text-slate-500 leading-tight truncate">the list they sent → the file the desk needs</div>
            </div>
          </div>
          <div className="hidden md:block"><Stepper step={step} /></div>
          {startTime && (
            <div className="flex items-center gap-3 shrink-0">
              <div className="flex items-center gap-1.5 text-slate-600"><Clock size={14} /><span className="sg-mono text-sm tabular-nums">{fmtClock(elapsed)}</span></div>
              <div className="hidden sm:flex items-center gap-1.5 text-slate-600"><MousePointerClick size={14} /><span className="sg-mono text-sm tabular-nums">{edits}</span><span className="text-xs text-slate-400">edits</span></div>
            </div>
          )}
        </div>
        <div className="md:hidden px-4 pb-2.5 overflow-x-auto"><Stepper step={step} /></div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6 sm:py-8">
        {step === "intake" && <Intake processing={processing} onProcess={startProcess} />}
        {step === "map" && <MapStep onBack={() => setStep("intake")} onNext={() => setStep("review")} />}
        {step === "review" && (
          <Review
            guests={guests} sel={sel} setSel={setSel} sourceRef={sourceRef} tally={tally}
            confirmField={confirmField} editField={editField} bulkSex={bulkSex} bulkCit={bulkCit} onApprove={approve}
          />
        )}
        {step === "files" && <Files guests={guests} elapsed={elapsed} edits={edits} onReset={reset} />}
      </main>

      <footer className="max-w-7xl mx-auto px-4 sm:px-6 pb-10 pt-2">
        <p className="text-[11px] leading-relaxed text-slate-400 max-w-3xl">
          Demo with sample data — nothing is transmitted. The hotelier remains responsible for reporting guests to the
          Questura within the legal window; Soglia prepares the files and assists. Reference codes shown are illustrative;
          production resolves against the official Alloggiati Web code tables.
        </p>
      </footer>
    </div>
  );
}

/* ── Step 1 · Intake ─────────────────────────────────────────────────────── */

function Intake({ processing, onProcess }) {
  return (
    <div className="sg-fade grid lg:grid-cols-[1.05fr_0.95fr] gap-6 lg:gap-10 items-center">
      <div>
        <div className="inline-flex items-center gap-1.5 text-[11px] sg-mono tracking-wide uppercase text-slate-500 bg-white border border-stone-200 rounded-full px-2.5 py-1">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" /> Group check-in
        </div>
        <h1 className="mt-4 text-3xl sm:text-4xl font-bold tracking-tight leading-[1.1]">
          A 50-name list takes the desk <span className="text-slate-400 line-through decoration-2">2½ hours</span>.<br />
          Soglia makes it a review.
        </h1>
        <p className="mt-4 text-slate-600 leading-relaxed max-w-xl">
          Groups send their guest list however they like — Word, PDF, Excel, pasted in an email. Soglia reads it once,
          shows you exactly what it found and where it found it, and hands you the file your PMS and the police portal
          actually accept. You approve every guest. Nothing is auto-submitted.
        </p>
        <ul className="mt-5 space-y-2 text-sm text-slate-600">
          {[
            ["Reads the file, never invents", "absent stays absent — no plausible guesses filling blanks"],
            ["Every value points back to its cell", "click any field to see the original it came from"],
            ["You approve, then download", "Alloggiati Web .txt, Bedzzle .xlsx, or a clean copy-paste sheet"],
          ].map(([a, b]) => (
            <li key={a} className="flex gap-2.5">
              <Check size={16} className="mt-0.5 text-emerald-600 shrink-0" strokeWidth={2.5} />
              <span><span className="font-semibold text-slate-800">{a}</span> — {b}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* incoming file card */}
      <div className="bg-white rounded-2xl border border-stone-200 shadow-sm p-5 sm:p-6">
        <div className="text-[11px] sg-mono uppercase tracking-wide text-slate-400">Incoming</div>
        <div className="mt-3 flex items-start gap-3">
          <div className="grid place-items-center w-11 h-11 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-700 shrink-0">
            <FileSpreadsheet size={22} />
          </div>
          <div className="min-w-0">
            <div className="font-semibold text-slate-800 truncate">Cantiere Milano Est — squadra giugno.xlsx</div>
            <div className="text-xs text-slate-500 sg-mono">Excel · 8 righe ospite · arrivata via email</div>
          </div>
        </div>

        {/* tiny mess preview */}
        <div className="mt-4 rounded-lg border border-stone-200 overflow-hidden">
          <div className="bg-stone-50 px-3 py-1.5 text-[10px] sg-mono text-slate-400 border-b border-stone-200">anteprima</div>
          <div className="p-3 sg-mono text-[10.5px] leading-[1.7] text-slate-500 overflow-x-auto">
            <div className="text-slate-700 font-semibold">CANTIERE MILANO EST — SQUADRA GIUGNO 2026</div>
            <div className="text-amber-700">Cittadinanza: ROMANIA</div>
            <div className="text-slate-400">Cognome · Nome · Data nascita · Luogo · Documento · Rilasciato il · Camera</div>
            <div>POPESCU · Ion · 14/03/1979 · Bucuresti · C.I. RO5582013 …</div>
            <div>IONESCU · Maria · 22/07/1985 · Cluj-Napoca · — …</div>
            <div className="text-red-600">CONSTANTIN · Elena · 30/02/1992 · Constanta · — …</div>
            <div className="text-slate-400">… +4 · <span className="italic">TOTALE: 8 PERSONE</span></div>
          </div>
        </div>

        <button
          onClick={onProcess}
          disabled={processing}
          className="mt-5 w-full flex items-center justify-center gap-2 rounded-xl bg-slate-900 text-white font-semibold py-3 hover:bg-slate-800 disabled:opacity-70 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2"
        >
          {processing ? (<><Wand2 size={17} className="sg-pulse" /> Reading the list…</>) : (<><Upload size={17} /> Process this list</>)}
        </button>
        <p className="mt-2.5 text-center text-[11px] text-slate-400">
          {processing ? "One model pass at the boundary — everything after this is plain, testable code." : "Drop your own later — this demo uses a sample crew list."}
        </p>
      </div>
    </div>
  );
}

/* ── Step 2 · Confirm columns (the guarded single point of failure) ──────── */

function MapStep({ onBack, onNext }) {
  const maps = [
    { col: "A", head: "Cognome", to: "Surname", note: "read straight", kind: "ok" },
    { col: "B", head: "Nome", to: "First name", note: "read straight", kind: "ok" },
    { col: "C", head: "Data di nascita", to: "Birth date", note: "format dd/mm/yyyy", kind: "ok" },
    { col: "D", head: "Luogo di nascita", to: "Birthplace", note: "resolved against place tables", kind: "ok" },
    { col: "E", head: "Documento", to: "Document (head only)", note: "type + number", kind: "ok" },
    { col: "F", head: "Rilasciato il", to: "Document issue date — ignored", note: "this is NOT a second birth date; the police format doesn't use it", kind: "watch" },
    { col: "G", head: "Camera", to: "Room", note: "kept for your records", kind: "ok" },
  ];
  return (
    <div className="sg-fade max-w-3xl mx-auto">
      <h2 className="text-2xl font-bold tracking-tight">First, confirm how we read your columns.</h2>
      <p className="mt-2 text-slate-600 max-w-2xl">
        This is the one judgment that matters most. A swapped or mislabelled column would turn 500 confident-looking
        values wrong at once — so you check the <em>reading</em>, not just the cells. Two seconds here, then the rest is review.
      </p>

      <div className="mt-6 bg-white rounded-2xl border border-stone-200 shadow-sm overflow-hidden">
        <div className="px-4 sm:px-5 py-3 border-b border-stone-200 flex items-center gap-2 text-sm text-slate-500">
          <Table2 size={15} /> <span className="sg-mono text-xs">Cantiere Milano Est — squadra giugno.xlsx</span>
        </div>
        <ul className="divide-y divide-stone-100">
          {maps.map((m) => (
            <li key={m.col} className="px-4 sm:px-5 py-3 flex items-center gap-3 sm:gap-4">
              <span className="grid place-items-center w-7 h-7 rounded-md bg-slate-900 text-white sg-mono text-xs shrink-0">{m.col}</span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="sg-mono text-sm text-slate-700">{m.head}</span>
                  <ArrowRight size={13} className="text-slate-300" />
                  <span className={`text-sm font-semibold ${m.kind === "watch" ? "text-amber-700" : "text-slate-900"}`}>{m.to}</span>
                </div>
                <div className={`text-xs mt-0.5 ${m.kind === "watch" ? "text-amber-700" : "text-slate-400"}`}>{m.note}</div>
              </div>
              {m.kind === "watch"
                ? <AlertTriangle size={16} className="text-amber-500 shrink-0" />
                : <Check size={16} className="text-emerald-600 shrink-0" strokeWidth={2.5} />}
            </li>
          ))}
        </ul>
      </div>

      {/* the things not in any column */}
      <div className="mt-4 grid sm:grid-cols-3 gap-3">
        <Flag icon={<Wand2 size={15} />} title="No sex column" body="We'll infer it from first names and mark it for your check — never silently." />
        <Flag icon={<MapPin size={15} />} title="No citizenship column" body="We'll fill it down from “Cittadinanza: ROMANIA” at the top of the sheet." />
        <Flag icon={<X size={15} />} title="“TOTALE: 8 PERSONE” row" body="Recognised as a totals line, not a guest — skipped." />
      </div>

      <div className="mt-5 flex items-center gap-3 rounded-xl bg-emerald-50 border border-emerald-200 px-4 py-3 text-sm text-emerald-900">
        <ShieldCheck size={18} className="shrink-0" />
        <span><span className="font-semibold">8 guest rows found</span> — same count we'll extract. If those two numbers ever disagree, the whole list is flagged.</span>
      </div>

      <div className="mt-6 flex flex-col-reverse sm:flex-row gap-3 sm:justify-between">
        <button onClick={onBack} className="text-sm font-medium text-slate-500 hover:text-slate-800 px-2 py-2.5">These are wrong — re-read</button>
        <button onClick={onNext} className="flex items-center justify-center gap-2 rounded-xl bg-slate-900 text-white font-semibold px-5 py-3 hover:bg-slate-800 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2">
          Looks right — review guests <ArrowRight size={16} />
        </button>
      </div>
    </div>
  );
}
function Flag({ icon, title, body }) {
  return (
    <div className="bg-white rounded-xl border border-stone-200 p-3.5">
      <div className="flex items-center gap-2 text-slate-700"><span className="text-slate-400">{icon}</span><span className="text-sm font-semibold">{title}</span></div>
      <p className="mt-1 text-xs text-slate-500 leading-relaxed">{body}</p>
    </div>
  );
}

/* ── Step 3 · Review (the product moment) ────────────────────────────────── */

function Review({ guests, sel, setSel, sourceRef, tally, confirmField, editField, bulkSex, bulkCit, onApprove }) {
  const reds = tally.r;
  const selField = sel ? guests[sel.gid].f[sel.key] : null;
  const inferredSexLeft = guests.filter((g) => g.f.sesso.tier !== "green").length;
  const inferredCitLeft = guests.filter((g) => g.f.cittadinanza.tier !== "green").length;

  return (
    <div className="sg-fade">
      {/* status row */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Review the guests</h2>
          <p className="text-sm text-slate-500 mt-0.5">Click any value to see where it came from. Resolve the reds, glance at the ambers, approve.</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Tile dot="bg-emerald-500" n={tally.g} label="verified" />
          <Tile dot="bg-amber-500" n={tally.y} label="to check" />
          <Tile dot="bg-red-500" n={tally.r} label="blocking" />
        </div>
      </div>

      {/* reconciliation + bulk actions */}
      <div className="mt-4 flex flex-col md:flex-row gap-3">
        <div className="flex items-center gap-2.5 rounded-xl bg-white border border-stone-200 px-4 py-2.5 text-sm">
          <ShieldCheck size={17} className="text-emerald-600 shrink-0" />
          <span className="text-slate-700"><span className="font-semibold">8 of 8</span> guests accounted for</span>
        </div>
        <div className="flex flex-wrap gap-2 items-center">
          <BulkBtn disabled={inferredSexLeft === 0} onClick={bulkSex} icon={<Wand2 size={14} />}
            label={inferredSexLeft === 0 ? "Sex confirmed" : `Confirm inferred sex (${inferredSexLeft})`} done={inferredSexLeft === 0} />
          <BulkBtn disabled={inferredCitLeft === 0} onClick={bulkCit} icon={<MapPin size={14} />}
            label={inferredCitLeft === 0 ? "Citizenship set" : `Set citizenship = Romania (${inferredCitLeft})`} done={inferredCitLeft === 0} />
        </div>
      </div>

      {reds > 0 && (
        <div className="mt-3 flex items-start gap-2.5 rounded-xl bg-red-50 border border-red-200 px-4 py-2.5 text-sm text-red-900">
          <CircleAlert size={17} className="shrink-0 mt-0.5" />
          <span><span className="font-semibold">{reds} {reds === 1 ? "value blocks" : "values block"} approval.</span> A red field is a missing or impossible value the file can't go out with — fix it against the guest's ID.</span>
        </div>
      )}

      {/* selected-field detail */}
      {selField && (
        <DetailCard key={`${sel.gid}-${sel.key}`} guests={guests} sel={sel} field={selField} onClose={() => setSel(null)} confirmField={confirmField} editField={editField} />
      )}

      {/* two panes */}
      <div className="mt-4 grid lg:grid-cols-2 gap-4">
        <OriginalPane highlight={sourceRef} />
        <ExtractedPane guests={guests} sel={sel} setSel={setSel} />
      </div>

      {/* approve */}
      <div className="mt-6 flex flex-col sm:flex-row items-center justify-end gap-3">
        {reds > 0 && <span className="text-sm text-slate-400">Resolve the {reds} red {reds === 1 ? "value" : "values"} to continue</span>}
        <button
          onClick={onApprove}
          disabled={reds > 0}
          className={`flex items-center justify-center gap-2 rounded-xl font-semibold px-6 py-3 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 ${reds > 0 ? "bg-stone-200 text-stone-400 cursor-not-allowed" : "bg-slate-900 text-white hover:bg-slate-800 focus-visible:ring-slate-900"}`}
        >
          <ShieldCheck size={17} /> Approve guest list
        </button>
      </div>
    </div>
  );
}

function Tile({ dot, n, label }) {
  return (
    <div className="flex items-center gap-1.5 rounded-lg bg-white border border-stone-200 px-2.5 py-1.5">
      <span className={`w-2 h-2 rounded-full ${dot}`} />
      <span className="sg-mono text-sm font-semibold tabular-nums">{n}</span>
      <span className="text-xs text-slate-400 hidden sm:inline">{label}</span>
    </div>
  );
}
function BulkBtn({ disabled, onClick, icon, label, done }) {
  return (
    <button onClick={onClick} disabled={disabled}
      className={`flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium border transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 ${done ? "bg-emerald-50 border-emerald-200 text-emerald-700" : "bg-white border-slate-300 text-slate-700 hover:border-slate-900 hover:text-slate-900 focus-visible:ring-slate-900"}`}>
      {done ? <Check size={14} strokeWidth={2.5} /> : icon}{label}
    </button>
  );
}

/* left: the original sheet, with the selected field's source cell lit ──── */

function OriginalPane({ highlight }) {
  const litCol = highlight && /^[A-G]\d+$/.test(highlight) ? highlight[0] : null;
  const litRow = highlight && /^[A-G]\d+$/.test(highlight) ? parseInt(highlight.slice(1), 10) : null;
  const isLit = (col, r) => col === litCol && r === litRow;
  const annotationLit = highlight === "annotation A2";

  return (
    <div className="bg-white rounded-2xl border border-stone-200 shadow-sm overflow-hidden flex flex-col">
      <PaneHead icon={<FileSpreadsheet size={14} />} title="The file they sent" sub="original, untouched" />
      <div className="overflow-auto max-h-[520px]">
        <table className="sg-mono text-[11px] sm:text-xs border-collapse w-full">
          <thead className="sticky top-0 z-10">
            <tr className="bg-stone-100 text-slate-400">
              <th className="w-7 border border-stone-200 font-normal py-1"> </th>
              {COLS.map((c) => <th key={c} className="border border-stone-200 font-normal py-1 px-2 text-left">{c}</th>)}
            </tr>
          </thead>
          <tbody className="text-slate-700">
            <tr>
              <RowNum n={1} />
              <td colSpan={7} className="border border-stone-200 px-2 py-1.5 font-semibold text-slate-800 bg-stone-50/60">{RAW.title}</td>
            </tr>
            <tr>
              <RowNum n={2} />
              <td colSpan={7} className={`border px-2 py-1.5 transition-colors ${annotationLit ? "bg-sky-100 border-sky-400 ring-1 ring-sky-400" : "border-stone-200 text-amber-700 bg-amber-50/40"}`}>{RAW.annotation}</td>
            </tr>
            <tr className="text-slate-400">
              <RowNum n={3} />
              {RAW.headers.map((h, i) => <td key={i} className="border border-stone-200 px-2 py-1.5 italic">{h}</td>)}
            </tr>
            {RAW.rows.map((row) => (
              <tr key={row.r}>
                <RowNum n={row.r} />
                {row.cells.map((cell, ci) => {
                  const lit = isLit(COLS[ci], row.r);
                  return (
                    <td key={ci} className={`border px-2 py-1.5 whitespace-nowrap transition-colors ${lit ? "bg-sky-100 border-sky-400 ring-1 ring-sky-400 text-sky-900 font-semibold" : "border-stone-200"} ${cell === "" ? "text-slate-300" : ""}`}>
                      {cell === "" ? "—" : cell}
                    </td>
                  );
                })}
              </tr>
            ))}
            <tr>
              <RowNum n={RAW.totalsRow} />
              <td colSpan={7} className="border border-stone-200 px-2 py-1.5 italic text-slate-400 bg-stone-50/60">TOTALE: 8 PERSONE</td>
            </tr>
          </tbody>
        </table>
      </div>
      {highlight && (
        <div className="px-4 py-2 border-t border-stone-200 bg-sky-50 text-[11px] text-sky-800 flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-sm bg-sky-400" /> showing source: <span className="sg-mono font-semibold">{highlight}</span>
        </div>
      )}
    </div>
  );
}
const RowNum = ({ n }) => <td className="bg-stone-100 text-slate-300 text-center border border-stone-200 px-1 select-none">{n}</td>;

/* right: the extracted canonical table, tier-coloured ──────────────────── */

const COLDEF = [
  { key: "cognome", label: "Cognome" },
  { key: "nome", label: "Nome" },
  { key: "sesso", label: "Sesso" },
  { key: "nascita", label: "Nascita" },
  { key: "luogo", label: "Luogo di nascita" },
  { key: "cittadinanza", label: "Cittadinanza" },
  { key: "documento", label: "Documento" },
];

function ExtractedPane({ guests, sel, setSel }) {
  return (
    <div className="bg-white rounded-2xl border border-stone-200 shadow-sm overflow-hidden flex flex-col">
      <PaneHead icon={<FileCheck2 size={14} />} title="What Soglia read" sub="grouped, ready to approve" />
      <div className="overflow-auto max-h-[520px]">
        <table className="text-xs border-collapse w-full">
          <thead className="sticky top-0 z-10">
            <tr className="bg-stone-100 text-slate-400 text-left">
              <th className="border border-stone-200 font-medium py-1.5 px-2 sg-mono">Ruolo</th>
              {COLDEF.map((c) => <th key={c.key} className="border border-stone-200 font-medium py-1.5 px-2 whitespace-nowrap">{c.label}</th>)}
            </tr>
          </thead>
          <tbody>
            {guests.map((g) => (
              <tr key={g.id} className="align-top">
                <td className="border border-stone-200 px-2 py-2 whitespace-nowrap">
                  <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] sg-mono ${g.roleCode === "18" ? "bg-slate-900 text-white" : "bg-stone-100 text-slate-500"}`}>
                    {g.roleCode === "18" ? "capo" : <><CornerDownRight size={10} /> membro</>}
                  </span>
                </td>
                {COLDEF.map((c) => {
                  const fld = g.f[c.key];
                  const isSel = sel && sel.gid === g.id && sel.key === c.key;
                  // members' empty doc fields render as a quiet, correct blank
                  if (c.key === "documento" && fld.value == null) {
                    return <td key={c.key} className="border border-stone-200 px-2 py-2 text-slate-300 sg-mono text-[11px]">— <span className="not-italic text-[10px]">(member)</span></td>;
                  }
                  const t = TIER[fld.tier];
                  return (
                    <td key={c.key} className="border border-stone-200 p-1">
                      <button
                        onClick={() => setSel(isSel ? null : { gid: g.id, key: c.key })}
                        className={`w-full text-left rounded-md border px-2 py-1.5 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 ${t.cell} ${isSel ? "ring-2 ring-sky-400" : ""}`}
                      >
                        <span className="flex items-center gap-1.5">
                          <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${t.dot}`} />
                          <span className="truncate sg-mono text-[11px]">{fld.value ?? "—"}</span>
                        </span>
                        {fld.origin === "inferred" && fld.tier !== "green" && <span className="block text-[9px] uppercase tracking-wide opacity-60 mt-0.5 pl-3">inferred</span>}
                        {fld.origin === "manual" && <span className="block text-[9px] uppercase tracking-wide opacity-60 mt-0.5 pl-3">you set this</span>}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="px-4 py-2 border-t border-stone-200 bg-stone-50 flex items-center gap-3 text-[11px] text-slate-500">
        <Legend dot="bg-emerald-500" t="verified" />
        <Legend dot="bg-amber-500" t="check" />
        <Legend dot="bg-red-500" t="blocks" />
      </div>
    </div>
  );
}
const Legend = ({ dot, t }) => <span className="flex items-center gap-1"><span className={`w-2 h-2 rounded-full ${dot}`} />{t}</span>;

function PaneHead({ icon, title, sub }) {
  return (
    <div className="px-4 py-2.5 border-b border-stone-200 flex items-center justify-between">
      <div className="flex items-center gap-2 text-slate-700"><span className="text-slate-400">{icon}</span><span className="text-sm font-semibold">{title}</span></div>
      <span className="text-[11px] sg-mono text-slate-400">{sub}</span>
    </div>
  );
}

/* the provenance + resolve card ───────────────────────────────────────── */

function DetailCard({ guests, sel, field, onClose, confirmField, editField }) {
  const g = guests[sel.gid];
  const label = COLDEF.find((c) => c.key === sel.key)?.label ?? sel.key;
  const t = TIER[field.tier];
  const [dateVal, setDateVal] = useState(field.value || "");
  const sourceText = field.source === "inferred" ? "Inferred — not in the file"
    : field.source === "annotation A2" ? "From the sheet header (A2)"
    : field.source ? `Cell ${field.source}` : "—";

  return (
    <div className="mt-4 sg-fade rounded-2xl border border-slate-300 bg-white shadow-md overflow-hidden">
      <div className="px-4 sm:px-5 py-3 bg-slate-900 text-white flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          <span className={`w-2.5 h-2.5 rounded-full ${t.dot}`} />
          <span className="font-semibold truncate">{g.f.nome.value} {g.f.cognome.value}</span>
          <ChevronRight size={14} className="text-slate-500" />
          <span className="text-slate-300 text-sm">{label}</span>
        </div>
        <button onClick={onClose} className="text-slate-400 hover:text-white p-1 rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-white"><X size={16} /></button>
      </div>

      <div className="p-4 sm:p-5 grid sm:grid-cols-[1fr_1.2fr] gap-4 sm:gap-6">
        <div>
          <Kv k="In your file">
            <span className="sg-mono text-slate-800">{field.verbatim ?? <span className="text-slate-400 italic">absent</span>}</span>
            <span className="block text-[11px] text-slate-400 mt-0.5">{sourceText}</span>
          </Kv>
          <Kv k="Soglia reads it as">
            <span className="sg-mono text-slate-800">{field.value ?? "—"}</span>
            {field.resolved && <span className="block text-[11px] text-emerald-700 mt-0.5">→ resolved: {field.resolved}</span>}
          </Kv>
          <div className="mt-2">
            <span className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[11px] font-semibold ${t.chip}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${t.dot}`} />{t.label}
              {field.origin === "inferred" ? " · inferred" : field.origin === "manual" ? " · you set this" : " · read from file"}
            </span>
          </div>
        </div>

        <div className="sm:border-l sm:border-stone-200 sm:pl-6">
          <div className="flex items-start gap-2 text-sm text-slate-600">
            <Info size={15} className="mt-0.5 text-slate-400 shrink-0" />
            <p className="leading-relaxed">{field.reason}</p>
          </div>

          {/* resolve controls by case */}
          <div className="mt-3.5">
            {field.tier === "red" && field.needsDate && (
              <div>
                <label className="text-[11px] text-slate-500 block mb-1">Correct date from the guest's ID</label>
                <div className="flex gap-2">
                  <input value={dateVal} onChange={(e) => setDateVal(e.target.value)} placeholder="gg/mm/aaaa"
                    className="sg-mono text-sm border border-slate-300 rounded-lg px-3 py-2 w-36 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900" />
                  <button onClick={() => editField(sel.gid, sel.key, dateVal.trim())}
                    disabled={!/^\d{2}\/\d{2}\/\d{4}$/.test(dateVal.trim())}
                    className="rounded-lg bg-slate-900 text-white text-sm font-semibold px-4 py-2 hover:bg-slate-800 disabled:opacity-40 transition-colors">Save</button>
                </div>
              </div>
            )}

            {field.tier === "red" && field.candidates && (
              <div>
                <div className="text-[11px] text-slate-500 mb-1.5">Which one? Pre-ranked — pick to resolve</div>
                <div className="flex flex-col gap-2">
                  {field.candidates.map((c, i) => (
                    <button key={c} onClick={() => editField(sel.gid, sel.key, c.split(",")[0], c)}
                      className="flex items-center justify-between gap-2 text-left rounded-lg border border-slate-300 px-3 py-2 text-sm hover:border-slate-900 hover:bg-stone-50 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900">
                      <span className="flex items-center gap-2"><MapPin size={14} className="text-slate-400" /><span className="sg-mono">{c}</span></span>
                      {i === 0 && <span className="text-[10px] sg-mono text-slate-400">most likely</span>}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {field.tier === "yellow" && (
              <button onClick={() => confirmField(sel.gid, sel.key)}
                className="flex items-center gap-2 rounded-lg bg-slate-900 text-white text-sm font-semibold px-4 py-2 hover:bg-slate-800 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900">
                <Check size={15} strokeWidth={2.5} />{sel.key === "nome" ? "Keep as written" : "Confirm this value"}
              </button>
            )}

            {field.tier === "green" && field.origin !== "manual" && (
              <div className="flex items-center gap-1.5 text-sm text-emerald-700"><Check size={15} strokeWidth={2.5} /> Nothing to do — verified.</div>
            )}
            {field.origin === "manual" && (
              <div className="flex items-center gap-1.5 text-sm text-emerald-700"><Check size={15} strokeWidth={2.5} /> Set by you · logged in the audit trail.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
function Kv({ k, children }) {
  return (
    <div className="mb-3">
      <div className="text-[11px] uppercase tracking-wide text-slate-400">{k}</div>
      <div className="mt-0.5 text-sm">{children}</div>
    </div>
  );
}

/* ── Step 4 · Files ──────────────────────────────────────────────────────── */

function downloadBlob(data, mime, filename) {
  const blob = new Blob([data], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; document.body.appendChild(a); a.click();
  document.body.removeChild(a); setTimeout(() => URL.revokeObjectURL(url), 1500);
}

function Files({ guests, elapsed, edits, onReset }) {
  const txt = useMemo(() => guests.map(trLine).join("\r\n"), [guests]); // CR+LF between, none trailing
  const manualMin = guests.length * 3; // honest per-guest baseline

  const cleanRows = guests.map((g) => ({
    Cognome: g.f.cognome.value, Nome: g.f.nome.value, Sesso: g.f.sesso.value,
    "Data di nascita": g.f.nascita.value, Cittadinanza: g.f.cittadinanza.value,
    "Luogo di nascita": g.f.luogo.resolved || g.f.luogo.value,
    "Tipo documento": g.roleCode === "18" ? "Carta d'identità" : "",
    "Numero documento": g.roleCode === "18" ? "RO5582013" : "",
    Camera: g.room,
  }));

  const dlXlsx = (rows, sheet, filename) => {
    const ws = XLSX.utils.json_to_sheet(rows);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, sheet);
    const out = XLSX.write(wb, { type: "array", bookType: "xlsx" });
    downloadBlob(out, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename);
  };

  return (
    <div className="sg-fade">
      {/* payoff */}
      <div className="rounded-2xl bg-slate-900 text-white p-5 sm:p-7 flex flex-col sm:flex-row sm:items-center justify-between gap-5">
        <div>
          <div className="inline-flex items-center gap-1.5 text-[11px] sg-mono uppercase tracking-wide text-emerald-300"><Check size={13} strokeWidth={3} /> Approved</div>
          <h2 className="mt-2 text-2xl sm:text-3xl font-bold tracking-tight">Done in {fmtClock(elapsed)}.</h2>
          <p className="mt-1.5 text-slate-300 max-w-xl text-sm leading-relaxed">
            8 guests, {edits} {edits === 1 ? "edit" : "edits"}, every value traceable to its source. By hand this crew is
            roughly <span className="text-white font-semibold">{manualMin} minutes</span> of field-by-field retyping —
            and a 50-name list is the ~2½-hour job this replaces. Messy lists take longer; clean ones, less.
          </p>
        </div>
        <div className="grid grid-cols-3 gap-3 shrink-0">
          <Stat n={fmtClock(elapsed)} l="this list" />
          <Stat n={`~${manualMin}m`} l="by hand" />
          <Stat n="8/8" l="traceable" />
        </div>
      </div>

      <h3 className="mt-7 text-lg font-bold tracking-tight">Your files</h3>
      <p className="text-sm text-slate-500">One approved list, three shapes — whatever this hotel's setup needs.</p>

      {/* tracciato — the signature */}
      <div className="mt-4 bg-white rounded-2xl border border-stone-200 shadow-sm overflow-hidden">
        <div className="px-4 sm:px-5 py-3 border-b border-stone-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className="grid place-items-center w-9 h-9 rounded-lg bg-slate-900 text-white shrink-0"><FileText size={18} /></div>
            <div>
              <div className="font-semibold text-slate-800">Alloggiati Web — police portal file</div>
              <div className="text-[11px] sg-mono text-slate-400">schedine.txt · 168 chars/line · UTF-8</div>
            </div>
          </div>
          <button onClick={() => downloadBlob(txt, "text/plain;charset=utf-8", "schedine_alloggiati.txt")}
            className="flex items-center justify-center gap-2 rounded-lg bg-slate-900 text-white text-sm font-semibold px-4 py-2.5 hover:bg-slate-800 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2">
            <Download size={15} /> Download .txt
          </button>
        </div>

        {/* legend */}
        <div className="px-4 sm:px-5 pt-3 flex flex-wrap gap-x-3 gap-y-1.5">
          {TR_FIELDS.map((f, i) => (
            <span key={f.k} className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] sg-mono ${SEG_TINT[i % SEG_TINT.length]}`}>
              {f.label}<span className="opacity-50">·{f.len}</span>
            </span>
          ))}
        </div>

        {/* the lines */}
        <div className="px-4 sm:px-5 py-4 overflow-x-auto">
          <div className="sg-mono text-[11px] leading-[2] min-w-max">
            {guests.slice(0, 3).map((g) => {
              const seg = trSegments(g);
              return (
                <div key={g.id} className="whitespace-nowrap flex items-center">
                  <span className="text-slate-300 mr-3 select-none w-16 inline-block">{g.roleCode === "18" ? "capo" : "membro"}</span>
                  {TR_FIELDS.map((f, i) => <Seg key={f.k} text={seg[f.k]} tint={SEG_TINT[i % SEG_TINT.length]} />)}
                </div>
              );
            })}
            <div className="text-slate-400 mt-1 pl-[4.75rem]">… righe 4–8 · {guests.length} schedine in the file</div>
          </div>
        </div>
        <div className="px-4 sm:px-5 py-2.5 border-t border-stone-200 bg-stone-50 text-[11px] text-slate-500 flex items-start gap-2">
          <Info size={13} className="mt-0.5 shrink-0" />
          <span>Every field padded to its exact width (dots = spaces). Group members carry blank document fields by rule; lines join with CR+LF and the last has none — one stray newline and the portal rejects the file.</span>
        </div>
      </div>

      {/* xlsx outputs */}
      <div className="mt-4 grid md:grid-cols-2 gap-4">
        <OutCard
          icon={<FileSpreadsheet size={18} />} title="Bedzzle rooming list" sub="bedzzle_import.xlsx"
          desc="The group-import template the PMS already accepts — the button hotels have but groups never fill."
          onDownload={() => dlXlsx(cleanRows, "Rooming", "bedzzle_import.xlsx")} rows={cleanRows}
        />
        <OutCard
          icon={<Table2 size={18} />} title="Clean copy-paste sheet" sub="lista_pulita.xlsx"
          desc="A tidy generic sheet for any other PMS — Opera, SAP, Scrigno — or a fast manual paste."
          onDownload={() => dlXlsx(cleanRows, "Ospiti", "lista_pulita.xlsx")} rows={cleanRows}
        />
      </div>

      {/* compliance loop note + reset */}
      <div className="mt-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 rounded-2xl bg-emerald-50 border border-emerald-200 px-5 py-4">
        <div className="flex items-start gap-2.5 text-sm text-emerald-900">
          <ShieldCheck size={18} className="shrink-0 mt-0.5" />
          <span>After you transmit, the portal's signed receipt is archived here permanently — it keeps only 30 days, you keep the proof. <span className="font-semibold">We delete the passports, we keep the proof of compliance.</span></span>
        </div>
        <button onClick={onReset} className="flex items-center gap-2 rounded-lg border border-emerald-300 bg-white text-emerald-800 text-sm font-semibold px-4 py-2.5 hover:bg-emerald-100 transition-colors shrink-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600">
          <RotateCcw size={15} /> Run another list
        </button>
      </div>
    </div>
  );
}

function Seg({ text, tint }) {
  return (
    <span className={`inline-block ${tint} mr-px px-px`} title={text}>
      {[...text].map((ch, i) => ch === " "
        ? <span key={i} className="opacity-25">·</span>
        : <span key={i}>{ch}</span>)}
    </span>
  );
}
function Stat({ n, l }) {
  return (
    <div className="text-center rounded-xl bg-white/10 px-3 py-2.5 min-w-[68px]">
      <div className="sg-mono text-lg font-semibold tabular-nums leading-none">{n}</div>
      <div className="text-[10px] uppercase tracking-wide text-slate-400 mt-1">{l}</div>
    </div>
  );
}
function OutCard({ icon, title, sub, desc, onDownload, rows }) {
  const cols = Object.keys(rows[0]);
  return (
    <div className="bg-white rounded-2xl border border-stone-200 shadow-sm overflow-hidden flex flex-col">
      <div className="px-4 sm:px-5 py-3 border-b border-stone-200 flex items-center gap-2.5">
        <div className="grid place-items-center w-9 h-9 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-700 shrink-0">{icon}</div>
        <div className="min-w-0">
          <div className="font-semibold text-slate-800 truncate">{title}</div>
          <div className="text-[11px] sg-mono text-slate-400 truncate">{sub}</div>
        </div>
      </div>
      <p className="px-4 sm:px-5 pt-3 text-xs text-slate-500 leading-relaxed">{desc}</p>
      <div className="px-4 sm:px-5 py-3 overflow-x-auto">
        <table className="text-[10.5px] sg-mono border-collapse">
          <thead><tr className="text-slate-400 text-left">{cols.slice(0, 4).map((c) => <th key={c} className="border border-stone-200 px-1.5 py-1 font-normal whitespace-nowrap">{c}</th>)}<th className="px-1.5 text-slate-300">…</th></tr></thead>
          <tbody>
            {rows.slice(0, 3).map((r, i) => (
              <tr key={i} className="text-slate-600">{cols.slice(0, 4).map((c) => <td key={c} className="border border-stone-200 px-1.5 py-1 whitespace-nowrap">{String(r[c]) || "—"}</td>)}<td className="px-1.5 text-slate-300">…</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-auto px-4 sm:px-5 py-3 border-t border-stone-200">
        <button onClick={onDownload} className="w-full flex items-center justify-center gap-2 rounded-lg bg-slate-900 text-white text-sm font-semibold py-2.5 hover:bg-slate-800 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2">
          <Download size={15} /> Download .xlsx
        </button>
      </div>
    </div>
  );
}
