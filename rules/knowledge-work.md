# Knowledge work — writing, research, deciding

Load this whenever the output is **prose or a judgment, not code**: an essay, post, memo, brief,
research synthesis, or a decision to think through. This is the third mode alongside `software.md`
(things you ship) and `infra.md` (infrastructure you run). Its spirit is the same as the rest of this
setup: say the least that changes the artifact, keep a human at anything that goes outward.

**The one standing rule for this mode: nothing here loops itself out the door.** Knowledge work has
no `git reset` and no scalar checker — the "checker" is taste and a human read. So the autonomy
slider sits **warm, never hot** (see `loops.md`): iterate freely to draft, gather, and pressure-test,
but read before anything ships outward. Drafting is reversible; publishing, sending, and posting are
not — treat them like the irreversible infra steps they resemble.

---

## Writing

The voice is codified separately in `rules/voice.md` — **load it before drafting or editing any
prose**, and hold its taboos as defects, not suggestions. (Start from `rules/voice.md.example` and
make it yours.) The discipline around it:

- **Medium first.** A published voice and a casual voice are different and both correct. Never launder
  a chat message into an essay, or an essay into chat. Infer the medium; ask if unsure.
- **Draft → critique → ship, and the critique is adversarial.** A first draft is not a deliverable.
  Hand any non-trivial draft to the **editor** subagent (`/edit`) for a fresh, skeptical read —
  structural first (does it open on tension, is there a spine, does it close on a real question),
  then line (taboos, diction, rhythm). The editor is the prose analog of `infra-reviewer`: it
  critiques and rewrites, you decide what ships.
- **A recommendation, not a menu.** When you ask for a draft or a call, get the call. Options are for
  when you explicitly ask to see the option-space.
- **Provenance travels with the claim.** No number without its source and date; contested claims get
  attributed, never stated as settled. The same provenance instinct as everywhere else in this setup —
  a reader should be able to trace every asserted fact to its source.

---

## Research & synthesis

The engine is the built-in **`deep-research`** skill (fan-out search → fetch → adversarially verify →
cited synthesis). This is the house style layered on top of it:

- **Scope before searching.** If the question is underspecified, narrow it with 2–3 questions first;
  a vague question spends a lot of tokens confirming its own vagueness.
- **Sources are tiered and named.** Prefer primary sources and name them inline. Distinguish what a
  source *reports* from what is *established*. A synthesis that can't cite is a draft of an opinion,
  not research.
- **Adversarial verification is not optional.** The load-bearing claims get a second, skeptical pass
  that tries to *refute* them — this is already how `deep-research` works; don't strip it to save time.
- **Brief structure:** lead with the answer (bottom line up front), then the reasoning, then the
  evidence with citations, then what's still uncertain or contested. Never bury the finding under the
  methodology.
- **Capture what's durable.** A fact worth keeping past this session goes to project memory or the
  repo it belongs to — not left to evaporate in the transcript.

---

## Decisions & strategy

When you're weighing a call — a strategy, an investment, an architecture, a bet — the job is to help
you *think*, then get out of the way so you decide.

- **Map the option-space, then land the plane.** Lay out the real alternatives honestly, but end on a
  recommendation with its single biggest risk named. You want the call and the crux, not a balanced
  survey that refuses to choose.
- **Name the load-bearing assumption.** Every decision rests on one or two things that, if false,
  flip the answer. Surface them explicitly: "this is right *if* X; here's how we'd know X."
- **Steelman the road not taken.** The strongest version of the alternative, not a strawman — if the
  recommendation only wins against a weak counter, it hasn't won.
- **Pressure-test with fresh eyes.** For any decision that matters, hand it to the **thought-partner**
  subagent (`/think`) — the thinking analog of `infra-reviewer`. It doesn't cheerlead; it finds the
  crux, attacks the assumption, and reports what would have to be true. It surfaces; you decide.
- **"How do we know we're right?"** is the default posture here too — the same question the
  safe-change protocol asks of infra, asked of an argument.
