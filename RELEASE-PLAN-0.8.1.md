# ExecWeave 0.8.1 implementation plan

> Baseline: `main` after 0.8.0 lands.
> This round changes the **collection layer**. It is the only round in this series that
> changes what an `.execweave` package contains.

---

## 0. Why

`filesystem.py` has never read the contents of a watched file — its only `read_text`
reads the inotify limit from sysfs. A `file` node carries no attributes at all, just an
edge saying created, modified or deleted.

That leaves a concrete blind spot:

```
write run.sh  →  bash run.sh  →  delete run.sh
```

`process.cmdline` holds only `['bash', 'run.sh']`. The content was in the file, and the
file is gone. All that survives is:

```
17:35  run.sh   created
17:35  process  bash run.sh
17:36  run.sh   deleted
```

**What ran is unknowable.**

By contrast, inline execution such as `bash -c "<script>"` already has its full text in
`cmdline` today (0.8.0 renders it). The blind spot is specifically
write-then-execute-then-delete, which is the case that most needs to be visible.

---

## 1. Capture

Read at the moment a create or modify is detected, without waiting for the next poll. A
delete uses the previous snapshot to determine what was removed.

### Limits belong in the capture stage, not only in the renderer

Capping only the view still lets the run directory grow without bound.

| limit | value | on exceeding |
|---|---|---|
| file size | 1 MB | no content; record the size change only |
| binary | contains NUL or is not UTF-8 | no content; record as binary |
| line length | 2000 characters | truncate that line and mark it |
| per-run diff budget | fixed | stop capturing and record that the budget was reached |

### Exclude self-observation

Without this the feature spends most of its time showing the tool watching itself. A real
run's three file nodes were:

```
.execweave-content-hyyj8gcj    created
.execweave-content-whq767zd    modified
semantic.jsonl.lock            deleted
```

Exclude the run directory itself, anything under `.execweave/`, the content store, and
`*.lock`.

---

## 2. The race, and what has to stay honest

The portable backend polls (`attributions: ["polling"]`). A create, execute and delete
that all happen inside one poll interval loses the content entirely.

No design removes that. It can only be narrowed: inotify on Linux, FSEvents on macOS.

**A miss must be recorded as content not captured, never as no change.** The two have to
be distinguishable at a glance:

```
17:35  run.sh   created   +42
17:36  run.sh   deleted    −42
```

versus

```
17:35  run.sh   created   content not captured (created and deleted 0.3 s apart,
                          shorter than the poll interval)
17:36  run.sh   deleted
```

Showing a miss as no change manufactures false confidence, which is worse than not having
the feature at all.

---

## 3. Presentation

### The node shows the shape of each change

Monospaced, counts right-aligned. Green applies only to the additions figure and red only
to the deletions figure; the verb and the filename stay in the normal colour.

```
17:35  report.md            created    +18
17:36  report.md                       +18   −3
17:38  src/viewer.py                    +2  −47
17:41  .env                 deleted           −6
18:02  data.csv             created    +12.4 KB binary · content not captured
```

Time only within a single day; a `08-31` style prefix appears when a run crosses midnight.

### Expanding shows hunks, not the file

Changed lines with a little context, capped at three hunks or forty lines, then:

```
… 12 more changes
```

### Repeated writes fold by round

Following the 0.8.0 rules — newest expanded, older folded:

```
▸ 17:23  +4 −0
▸ 17:24  +1 −9
▾ 17:26  +18 −3      ← newest
```

---

## 4. On by default

The privacy control belongs on **which directory is watched**, not on **whether contents
are read**. A tool whose purpose is to show what agents actually did on your machine
should not ship with the case that most needs watching turned off.

---

## 5. Red lines

1. Never show content that was not actually read.
2. "Not captured" and "no change" must stay distinct and must never stand in for each
   other.
3. Limits belong in the capture stage.
4. All v0.7.9 and v0.8.0 boundaries continue to apply: one renderer, completion never
   replaces the DOM, a conversation belongs to an agent, the main dashboard does not
   regain the retired controls.
5. Every item needs a Chromium behaviour check.

---

## 6. Verification

- a fixture that creates a file, modifies it three times, and deletes it
- a race fixture where creation and deletion are closer together than the poll interval
- browser: the format, colour and alignment of each row in the node panel
- browser: repeated writes show only the newest expanded
- browser: "content not captured" and "no change" are distinguishable on the page
- reverted: remove the limits and assert that capture stops once the run directory exceeds
  its budget
