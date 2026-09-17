# Issue 830 (2026-09-18) — Issue 829's anchor class, one seam deeper: the locale-I/O classifier was anchored to a CALL-NAME SET, and it repaired one side of a round trip in its own tracked instrument

**Status: RESOLVED same day (T1–T5).**
**Severity: a tracked instrument in this repo WRITES a fixture with the system
locale and READS it back as UTF-8 — Issue 829's exact defect, surviving Issue
829's own repair.**
**Origin: read the residual of Issue 829 instead of trusting its count.**

## The symptom

Issue 829 closed with **273 → 2**, the 2 outside the contract, the gate walled
at 0 and the sweep ratcheted. Every number in that record is correct. It is
also a count of **three call names**.

`cfg_row_implication_audit.py` is a tracked instrument in the docs gate's
dependency closure. Its selftest, at line 407:

```python
with tempfile.NamedTemporaryFile("w", suffix=".rs", delete=False) as fh:
    fh.write(body)
    name = fh.name
try:
    return leading_inner_cfgs(name)
```

and `leading_inner_cfgs`, in the same file, line 192:

```python
text = Path(path).read_text(encoding="utf-8", errors="replace")
```

The read side carries an explicit `encoding=`. **Issue 829 put it there.** The
write side is `tempfile.NamedTemporaryFile("w", …)`, which encodes with
`locale.getencoding()` — and is not `write_text`, not `read_text`, and not the
builtin `open`, so the classifier never saw it.

That is a **round-trip mismatch inside one file**: a cp874 write followed by a
UTF-8 read, twelve lines apart, half of it repaired by the issue whose entire
subject was that mismatch. The fixture bodies are ASCII today, so it passes —
which is Issue 829's own canonical failure verbatim, *"a test suite that had
been green for the wrong reason … it stayed invisible until an arm was written
whose subject was the corrupted character."*

## The finding

`locale_io_fix.sites()` reads:

```python
PATH_METHODS = {"write_text", "read_text"}
...
elif isinstance(node.func, ast.Name) and node.func.id == "open":
```

The class is **a text-mode file object whose encoding defaults to the locale**.
The predicate is **three names**. Everything else that constructs one was
invisible:

| form | why it is in the class |
|---|---|
| `p.open("w")` | `Path.open` / `io.open`, text mode |
| `tempfile.NamedTemporaryFile("w", …)` | text mode; the default `"w+b"` is safe, an explicit text mode is not |
| `os.fdopen(fd, "w")` | text mode; default `"r"` is text too |
| `io.TextIOWrapper(fh)` | always text |
| `codecs.open(p, "w")` | encoding is positional there |

This is the **fourth** time a rule in this family has been found anchored to
one representation of its own subject — Issue 823 (anchored to a POSITION),
Issue 828 (anchored to a DELIMITER SET), Issue 787 (a census anchored to the
DOCUMENT), and now a classifier anchored to a NAME SET. The shape is not that
somebody was careless; it is that **a classifier's coverage is only ever
testable against inputs somebody thought to write down**, and the cheapest
probe for it is to enumerate the class's *mechanism* and ask what else
produces it.

## What was measured (T1, before anything was claimed)

An AST probe over tracked `*.py` in all 16 checked-out contract repos, for
every attribute call that can produce a locale-encoded text handle:

```
    7  .open(<text mode literal>)         katgpt-rs 0 · riir-train 6 · riir-clippy 1
    2  tempfile.NamedTemporaryFile TEXT   katgpt-rs 2
    2  os.fdopen TEXT                     katgpt-rs 2
    0  io.TextIOWrapper
    0  codecs.open
   11  TOTAL real sites
```

**Four of the eleven are in this repo's own instruments, and all four write a
fixture some other code then reads**: the two `NamedTemporaryFile` rows write
a `.rs` and a `.yml` that the same selftest parses back, and the two
`os.fdopen` rows in `trap_exit_launder_audit.py` write **shell scripts that
`bash` then executes** — where a cp874 body is not mojibake in a comparison,
it is a script the interpreter reads as garbage.

## T2 — the discriminator, and its blind spot is MEASURED rather than argued

`.open` cannot be duck-typed by name the way `read_text` can. The workspace
carries `os.open`, `tarfile.open`, `Image.open` — none of them text files, all
of them `ast.Attribute` with `attr == "open"`. The existing classifier's stance
(*"`sock.read_text(x)` — duck-typed: the name IS the population"*) does not
transfer, because that name is Path-specific and `open` is not.

The discriminator is a **literal text-mode argument**: a `Constant` `str` whose
characters are a subset of `rwxat+U` and which is non-empty. It excludes, in
one rule and with no denylist of module names:

| excluded | by what |
|---|---|
| `os.open(devnull, os.O_WRONLY)` | mode is not a string literal |
| `tarfile.open(arc)` | no mode argument |
| `tarfile.open(path, "r:gz")` | `:` is not a file-mode character |
| `Image.open(hero_path)` | no mode argument |
| `f.open("rb")` | `b` |

⚠ **Its cost is the no-mode case**: `p.open()` defaults to text `"r"` and IS in
the class, and this rule cannot see it. That cost is not estimated — the probe
counted it. **5 sites workspace-wide carry a no-mode `.open`, and all 5 are the
table above.** The blind spot and the false-positive exclusion are the same
set, and today that set is 5/5 not-in-class. A denylist of receiver names would
have caught the no-mode case and would fail OPEN on the next library somebody
imports, against a gate walled at 0 with a deliberately empty exemptions file —
a false positive there is a red build, not a report.

The rule is the same shape as the one `locale_io_fix` already documents for
`**kwargs`: *"counts as UNKNOWN and is left alone … this repair may only ever
be conservative."* The blind spot is printed, not remembered.

## T3 — the repair

`locale_io_fix.sites()` gains the three forms behind `_text_mode()`. **One
classifier, still** — the gate, the sweep and the repair tool share it, so
there is no second copy to drift (Issue 755's rule, and the reason 829 was
built this way).

`repair()` needed **no change**: every new form accepts an `encoding=` keyword
and the insertion point is the same last-argument rule.

Arms: 12 new cases in `locale_io_fix.selftest()` — each new form positive, each
measured negative above, `mode=` as a keyword, a `b` mode by keyword, and the
idempotence re-run.

## T4 — the eleven sites

This repo's four, in the landing commit. The seven siblings, each cited by SHA
per the Issue-798 rule (*a cross-repo repair is not landed until it is
COMMITTED in the sibling repo*):

| repo | sites | commit |
|---|---|---|
| riir-train | 6 | `15db2c67` |
| riir-clippy | 1 | `54b999de` |

## T5 — the floors move, in the direction that proves the walk grew

`FLOOR_IO_CALLS` 450 → re-pinned on the measured count; the per-repo sweep
rows likewise. A floor that did not move would mean the new forms found
nothing.

## What this issue does NOT claim

- That the FILE seam is now closed. `codecs.open` and `io.TextIOWrapper` are
  implemented and measured at **0 sites**, so they are walls with no load on
  them yet; `p.open()` with no mode is a **stated** blind spot with a measured
  cost of 0. Both are re-measured on every sweep run rather than remembered.
- That a name-based classifier is wrong in general. `read_text` is
  Path-specific and duck-typing it is correct. `open` is not, and the
  difference is the whole of T2.
