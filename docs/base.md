# Ferrule v5 — Final Pass

Checked the compiled PDF. **Everything structural landed**: Figure 2 is four
frames, figures sit inline, Table II sums (78 = 0+68+10, 291 = 8+172+111),
Table III sums to 99, every cross-reference resolves, the `F` placeholders are
gone, and cJSON reads 68/10 in all four places.

Four things remain. **Part B is the big one** — it affects roughly thirty
sentences and is the main thing standing between this and a clean read.

---

# PART A — Text that is truncated or overflowing

Three places where content runs past the column and gets cut or wrapped badly.

## A1 — `git_signature_free` is truncated mid-word

In the PDF this renders as `git_signature_fre` — the last character falls off
the column. **Find:**

```latex
834 exported functions and recovered the duplicate/free pairs
(\texttt{git\_reference\_dup}/\texttt{git\_reference\_free},
\texttt{git\_object\_free}, \texttt{git\_signature\_dup}/\texttt{git\_signature\_free})
that constitute its handle discipline, a fourth idiom distinct from the
returned-handle and out-parameter forms.
```

**Replace with:**

```latex
834 exported functions and recovered the duplicate/free pairs that constitute
its handle discipline---\texttt{git\_reference\_dup} with
\texttt{git\_reference\_free}, \texttt{git\_signature\_dup} with
\texttt{git\_signature\_free}, and \texttt{git\_object\_free} over the generic
object type---a fourth idiom distinct from the returned-handle and
out-parameter forms.
```

## A2 — The `Evidenced` listing wraps badly

Renders as `// (rarely applicable; see` / `3.2)` across two lines, and `3.2`
should be a section reference anyway. **Find:**

```latex
\begin{lstlisting}
Evidenced {
    value       // the inferred fact
    sources     // which layer(s) produced it
    confidence  // 0.0 - 1.0, for inspection
    verified    // confirmed against the .so?
                //   (rarely applicable; see
3.2)
}
\end{lstlisting}
```

**Replace with:**

```latex
\begin{lstlisting}
Evidenced {
    value       // the inferred fact
    sources     // which layer produced it
    confidence  // 0.0-1.0, for inspection
    verified    // confirmed against the .so
                // (rarely applicable)
}
\end{lstlisting}
```

## A3 — The RQ3 transcript and protocol listing wrap

Two listings overflow. **First, find:**

```latex
\begin{lstlisting}
MCP     : {"handle": 1, "status": 0}
Python  : (1, 0)                   # (handle, status)
gRPC    : OpenResponse {handle: 1, status: 0}
\end{lstlisting}
```

**Replace with:**

```latex
\begin{lstlisting}[basicstyle=\ttfamily\scriptsize]
MCP    : {"handle": 1, "status": 0}
Python : (1, 0)          # (handle, status)
gRPC   : OpenResponse {handle: 1, status: 0}
\end{lstlisting}
```

**Second, find** the transcript line:

```latex
Delete(root 1)        -> freed 1 | invalidated [2] | live: 0
```

**Replace with:**

```latex
Delete(root 1)        -> freed 1 | invalidated [2]
```

---

# PART B — Em-dashes were stripped throughout

Something in your editing pipeline is removing `---`. The PDF has roughly thirty
sentences where a parenthetical lost both its dashes and the clauses ran
together. Examples of how it reads now:

> *"Ravitch et al. recover the resource-manager pattern which functions acquire
> and release a resource but not whether a returned pointer transfers ownership"*

> *"Ferrule exposes one the cJSON_InitHooks case of §IV-B and refuses the
> remaining 12"*

> *"it is a set of named shapes an unresolved pointer, an unmanaged void*, a
> destructor reached only conditionally for which the analysis has no contract"*

Each is unreadable on first pass. **When you paste the replacements below, check
that `---` survives** — if your editor converts it, type three hyphens manually.

Apply each of these. Left column is what's in your `.tex` now; right is the fix.

### Introduction

| Find | Replace |
|---|---|
| `heterogeneous assembled from several languages and runtimes and exposed` `over more than one protocol at once and every one of them that wants to` | `heterogeneous---assembled from several languages and runtimes, exposed` `over more than one protocol at once---and every one of them that wants to` |
| `libraries cJSON, compact and written by one team in one convention, and` `the public C API of SQLite, an order of magnitude larger and built over` `decades in a distinct convention then run the analysis on five` | `libraries---cJSON, compact and written by one team in one convention, and` `the public C API of SQLite, an order of magnitude larger and built over` `decades in a distinct convention---then run the analysis on five` |
| `three integration contexts that differ fundamentally a typed microservice` `boundary, an AI tool-use boundary, and a direct in-process call and enforce a` | `three integration contexts that differ fundamentally---a typed microservice` `boundary, an AI tool-use boundary, and a direct in-process call---and enforce a` |

### §II Taxonomy

| Find | Replace |
|---|---|
| `et al.\ recover the resource-manager pattern which functions acquire and` `release a resource but not whether a returned pointer transfers ownership to` | `et al.\ recover the resource-manager pattern---which functions acquire and` `release a resource---but not whether a returned pointer transfers ownership to` |

### §III Approach

| Find | Replace |
|---|---|
| `and is refused` `for a reason unrelated to safety which is the single largest` `source of refusals` | `and is refused` `for a reason unrelated to safety---which is the single largest` `source of refusals` |
| `is destructive on a stateful library probing SQLite's` | `is destructive on a stateful library: probing SQLite's` |
| `A function is` `\textbf{refused} left unbound, with a specific human-readable reason if any` `of three conditions holds:` | `A function is` `\textbf{refused}---left unbound, with a specific human-readable reason---if any` `of three conditions holds:` |

### §IV Evaluation

| Find | Replace |
|---|---|
| `The remaining five zlib~\cite{b18}, libpng~\cite{b19}, libpq~\cite{b20},` | `The remaining five---zlib~\cite{b18}, libpng~\cite{b19}, libpq~\cite{b20},` |
| `libgit2~\cite{b21}, and libxml2~\cite{b24} are \emph{blind}` | `libgit2~\cite{b21}, and libxml2~\cite{b24}---are \emph{blind}` |
| `runs a missing entry in the C type registry, and a type-match guard on` `lifecycle forwarding so those four figures are post-fix.` | `runs---a missing entry in the C type registry, and a type-match guard on` `lifecycle forwarding---so those four figures are post-fix.` |
| `permitting or forbidding any operation most` `commonly a function labelled` | `permitting or forbidding any operation---most` `commonly a function labelled` |
| `The root` `cause is named and the fix is mechanical extend the guard to inspect members` `recursively but we report the figure as measured` | `The root` `cause is named and the fix is mechanical---extend the guard to inspect members` `recursively---but we report the figure as measured` |
| `cJSON functions with bare \texttt{ctypes} exactly what a type-directed` `generator emits from the header and executed three sequences Ferrule refuses,` | `cJSON functions with bare \texttt{ctypes}---exactly what a type-directed` `generator emits from the header---and executed three sequences Ferrule refuses,` |
| `The` `third passing a Python \texttt{str} where the library expects a writable` `\texttt{char*} buffer completed silently` | `The` `third---passing a Python \texttt{str} where the library expects a writable` `\texttt{char*} buffer---completed silently` |
| `Ferrule exposes one the` `\texttt{cJSON\_InitHooks} case of \S\ref{sec:rq0} and refuses the remaining` | `Ferrule exposes one---the` `\texttt{cJSON\_InitHooks} case of \S\ref{sec:rq0}---and refuses the remaining` |
| `computational helpers version queries and byte-order conversions such as` `\texttt{png\_get\_uint\_32} that take no handle and correctly receive none.` | `computational helpers---version queries and byte-order conversions such as` `\texttt{png\_get\_uint\_32}---that take no handle and correctly receive none.` |
| `handle-lifecycle analysis produces no` `verdicts at all correctly, because there is no library-managed handle to` `track.` | `handle-lifecycle analysis produces no` `verdicts at all---correctly, because there is no library-managed handle to` `track.` |
| `verdicts for 28 handle types among them \texttt{\_xmlDoc},` | `verdicts for 28 handle types---among them \texttt{\_xmlDoc},` |
| `\texttt{\_xmlRegexp} and traced ownership through them, marking` | `\texttt{\_xmlRegexp}---and traced ownership through them, marking` |
| `analyzing partial ASTs the same guard introduced after the \texttt{stddef.h}` | `analyzing partial ASTs---the same guard introduced after the \texttt{stddef.h}` |
| `it is a set of` `named shapes an unresolved pointer, an unmanaged \texttt{void*}, a destructor` `reached only conditionally for which the analysis has no contract to express.` | `it is a set of` `named shapes---an unresolved pointer, an unmanaged \texttt{void*}, a destructor` `reached only conditionally---for which the analysis has no contract to express.` |
| `handle~1 is destroyed a use-after-free no ownership check can catch, because` | `handle~1 is destroyed---a use-after-free no ownership check can catch, because` |
| `A conformance suite of six` `sequences the borrowed-free refusal, the cascade-invalidated child above, a` | `A conformance suite of six` `sequences---the borrowed-free refusal, the cascade-invalidated child above, a` |
| `free of an owned root, and a successful round trip is run through every` | `free of an owned root, and a successful round trip---is run through every` |
| `the ${\sim}0.5$~$\mu$s added by the full Ferrule wrapper of which handle-table lookup is ${\sim}0.05$~$\mu$s represents well under 1\%` | `the ${\sim}0.5$~$\mu$s added by the full Ferrule wrapper---of which handle-table lookup is ${\sim}0.05$~$\mu$s---represents well under 1\%` |

### §V Discussion

| Find | Replace |
|---|---|
| `the label reflects our reading of its implementation the` `same artifact Ferrule reads so agreement there is weaker evidence than` | `the label reflects our reading of its implementation---the` `same artifact Ferrule reads---so agreement there is weaker evidence than` |
| `the parameter that triggered` `it \texttt{PQconnectdb: returns an unmanaged pointer whose pointee type could` `not be resolved} which is a statement a human can act on directly.` | `the parameter that triggered` `it---\texttt{PQconnectdb: returns an unmanaged pointer whose pointee type could` `not be resolved}---which is a statement a human can act on directly.` |
| `not the number of refused functions on libpq, four reasons` `against 122 refused functions.` | `not the number of refused functions---on libpq, four reasons` `against 122 refused functions.` |
| `a refusal carrying a reason is more useful than no tool at` `all not that the bound fraction is always high.` | `a refusal carrying a reason is more useful than no tool at` `all---not that the bound fraction is always high.` |

**After applying**, verify none were silently converted:

```bash
grep -c -- "---" ferrule.tex    # should be ~30, not 0
```

---

# PART C — A dangling forward reference

§III-C promises an example that §V never delivers. **Find:**

```latex
leak arises only when a genuine ownership-\emph{transfer} function is
misclassified as borrowed (\S\ref{sec:discussion} gives
\texttt{cJSON\_DetachItemViaPointer} as one such case).
```

Nothing in §V mentions `cJSON_DetachItemViaPointer`. Since RQ0 now measures
the leak rate directly, point there instead. **Replace with:**

```latex
leak arises only when a genuine ownership-\emph{transfer} function is
misclassified as borrowed---\texttt{cJSON\_DetachItemFromObject} is one such
case, where the caller does take ownership of the detached node.
```

---

# PART D — Small corrections

## D1 — "held-out" and "blind" are used for the same libraries

Methodology now calls all five blind, but three places still say held-out.

| Find | Replace |
|---|---|
| `\item \textbf{RQ2 (generalization).} On held-out libraries, and on one` `library run blind after the analysis was frozen, do the same` | `\item \textbf{RQ2 (generalization).} On the five libraries the analysis was` `never adapted to, do the same` |
| `\subsubsection{Breadth: does the fail-safe hold on held-out libraries?}` | `\subsubsection{Breadth: does the fail-safe hold on unseen libraries?}` |
| `\caption{Held-out libraries. ``Idiom'' is the dominant handle-management` | `\caption{The four blind libraries analyzed before freezing; libxml2 is reported separately in \S\ref{sec:blind}. ``Idiom'' is the dominant handle-management` |
| `not.} Two defects surfaced only under the held-out libraries.` | `not.} Two defects surfaced only under the blind libraries.` |
| `libpq  & Cross-type free misread as destroying the connection & memory safety & unsafe & held-out breadth run \\` | `libpq  & Cross-type free misread as destroying the connection & memory safety & unsafe & breadth run \\` |

## D2 — `\paragraph` renders as "a) Summary.:"

IEEEtran numbers `\paragraph` inside a subsubsection. Two places.

**Find:**

```latex
\paragraph{Summary.} Across seven libraries spanning six handle idioms, the
```

**Replace with:**

```latex
\textbf{Summary.} Across seven libraries spanning six handle idioms, the
```

**Find:**

```latex
  \paragraph{Memory footprint.}
```

**Replace with:**

```latex
\textbf{Memory footprint.}
```

## D3 — Table IV's caption misdescribes its last four rows

The variadic row is attributed to "several" libraries including SQLite, a
calibration library, so "exposed only by libraries the analysis was not adapted
to" is wrong for it. **Find:**

```latex
memory-safety). cJSON and SQLite are the calibration libraries; the last four
rows were exposed only by libraries the analysis was not adapted to.
```

**Replace with:**

```latex
memory-safety). cJSON and SQLite are the calibration libraries; the last four
rows were exposed only after the calibration pair, three of them by libraries
the analysis was never adapted to and one by the ground-truth audit.
```

## D4 — Two different 12s a reader will conflate

§IV-D says Ferrule "refuses the remaining 12" unsafe-to-expose functions.
Table III says 12 false refusals. These are disjoint sets that happen to be the
same size, and a reader will read the second as the first.

**Find:**

```latex
refuses the remaining 12 with a stated reason. The comparison is not that Ferrule
is safe and \texttt{ctypes} is not; it is that on this sample the two differ by 12
functions that a caller could invoke into undefined behavior with no diagnostic
at any layer.
```

**Replace with:**

```latex
refuses the remaining 12 with a stated reason. These 12 are distinct from the 12
false refusals of Table~\ref{tab:accuracy}, which are safe functions wrongly
declined; Ferrule refuses 24 of the 99 sampled functions in total, half of them
correctly. The comparison is not that Ferrule is safe and \texttt{ctypes} is
not; it is that on this sample the two differ by 12 functions a caller could
invoke into undefined behavior with no diagnostic at any layer.
```

## D5 — "verdict accuracy" excludes refusals by its own definition

The Correct column includes correctly-refused functions, which have no ownership
or lifecycle verdict to match. **Find:**

```latex
second is a safety property: \emph{verdict accuracy}, the fraction whose
ownership and lifecycle verdicts both match the label;
```

**Replace with:**

```latex
second is a safety property: \emph{verdict accuracy}, the fraction where the
ownership and lifecycle verdicts both match the label, or where the analysis
refused a function the label also marks unsafe to expose;
```

---

# FINAL CHECK

```bash
pdflatex ferrule.tex && pdflatex ferrule.tex
grep -c "Overfull" ferrule.log        # aim for under ~5
grep -c -- "---" ferrule.tex          # should be ~30
grep -n "DetachItemViaPointer" ferrule.tex   # must be empty
grep -n "held-out" ferrule.tex        # must be empty
grep -n "paragraph{Summary\|paragraph{Memory" ferrule.tex  # must be empty
```

Read these three passages in the PDF and confirm they parse on first read:

- §II-D, the Ravitch paragraph ("recover the resource-manager pattern---which…")
- §IV-D, the last paragraph (the two 12s)
- §IV-I, the closing sentence ("a set of named shapes---an unresolved pointer…")

If those three read cleanly, the em-dash pass worked everywhere.

---

# What's left after this

Nothing blocking. The two things that would strengthen the paper further, in
order of value per hour:

1. **A second labeller on 30 of the 99 functions.** The
   `audit_*_blind_annotator2.csv` sheets already exist. Cohen's κ closes the
   reviewer's objection 9 entirely, and it's an afternoon of someone else's
   time.

2. **The libpq extraction fix.** You now state in §IV-G that libpq's 26% is an
   implementation limitation rather than a fundamental one. Closing it would
   move the weakest number in the paper and validate the claim in the same
   stroke.