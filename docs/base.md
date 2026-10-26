# Ferrule v6 — step-by-step fixes

Each item gives the text to find in your `.tex` and what to replace it with.
Work top to bottom; later items assume earlier ones are applied.

**Decisions baked into this guide.** Memory-unsafety is reported separately
from exposability disagreement (only 1 of 7 "unsafe" verdicts corrupts memory).
Accuracy and false refusals are reported **by draw**, because the original
sample's refused stratum is stale; the safety counts are pooled at n=226,
which is valid since a stale refused stratum biases false refusals, not bound
verdicts.

**Regenerate first**, so the numbers below match your files:

```bash
cd ~/header-intent
python3 eval/04b_tally_audit.py \
  --pairs eval_output/audit/audit_cjson_blind.csv:eval_output/audit/audit_cjson_key.csv \
  --pairs eval_output/audit/audit_sqlite_blind.csv:eval_output/audit/audit_sqlite_key.csv \
  --pairs eval_output/audit/audit_zlib_blind.csv:eval_output/audit/audit_zlib_key.csv \
  --pairs eval_output/audit/audit_libpng_blind.csv:eval_output/audit/audit_libpng_key.csv \
  --pairs eval_output/audit/audit_libpq_blind.csv:eval_output/audit/audit_libpq_key.csv \
  --pairs eval_output/audit/audit_libgit2_blind.csv:eval_output/audit/audit_libgit2_key.csv \
  --pairs eval_output/audit/audit_libxml2_blind.csv:eval_output/audit/audit_libxml2_key.csv
python3 eval/04f_unsafe_breakdown.py
python3 eval/04e_split_score.py
python3 coverage_table.py esc
```

---

# FIX 1 — Abstract, final paragraph

**Find:**

```latex
We evaluate on seven C libraries totalling 2{,}334 exported functions. Two are
calibration libraries the analysis was developed against; the other five, ran
after the implementation was frozen at a recorded commit, were never adapted to.
Across those five the analysis binds 1{,}436 of 1{,}965 exported functions. The
framework demonstrated strong generalizability across the blind test set: 4 out
of 5 blind libraries achieved \textgreater 70\% coverage, with an adjusted
aggregate coverage of 77\%. The evaluation isolates seventeen conventions under
which a plausible binding heuristic misfires, eight of them
memory-safety-critical, and we report them as a catalogue for the next author
rather than as incidents.
```

**Replace with:**

```latex
We evaluate on seven C libraries totalling 2{,}334 exported functions. Two are
calibration libraries the analysis was developed against; the other five were
never adapted to, and all figures come from a single frozen commit. Across
those five the analysis binds 1{,}483 of 1{,}965 exported functions, with
per-library coverage in a narrow band from 70\% to 78\%. Against hand-labelled
ground truth for 226 functions, one verdict permits an operation that corrupts
memory (0.4\%, 95\% CI $[0.1\%, 2.5\%]$); fifteen forgo a legitimate free,
which is the direction the fail-safe is designed to fail in. A bare
\texttt{ctypes} binding of the same library aborts the process on two of three
unsafe sequences and silently corrupts the heap on the third. We compare
against three alternatives on the same labelled sample and the same scorer: a
type-directed filter, an operationalisation of the closest prior system, and
two frontier language models. The evaluation isolates twenty-two conventions
under which a plausible binding heuristic misfires, ten of them
memory-safety-critical, and we report them as a catalogue for the next author
rather than as incidents.
```

---

# FIX 2 — Introduction, the coverage-variance paragraph

**Find:**

```latex
we measure both directly against hand-labelled ground truth (\S\ref{sec:rq0}).
How much of an API Ferrule can bind varies widely with the library's
conventions. Every library we analyzed contributed at least one convention on
which a heuristic calibrated against the others misfires.
```

**Replace with:**

```latex
we measure both directly against hand-labelled ground truth (\S\ref{sec:rq0}).
Coverage turns out to be remarkably uniform across the five libraries the
analysis was never adapted to, between 70\% and 78\%, once each library's
include paths are correct; \S\ref{sec:coverage-blind} reports what happened
when they were not. What does vary is which conventions defeat a given
heuristic: every library we analyzed contributed at least one on which a
heuristic calibrated against the others misfires.
```

---

# FIX 3 — Introduction, contribution 2

**Find:**

```latex
adapted to} (\S\ref{sec:eval}). We report accuracy against hand-labelled ground
truth (78\% correct, one unsafe error in 99 functions), coverage by library
(26--87\%), whether a realistic program can be written entirely from the bound
subset, and a comparison against the signature-only binding a type-directed
generator produces, measured over the same labelled sample.
```

**Replace with:**

```latex
adapted to} (\S\ref{sec:eval}). We report accuracy against hand-labelled ground
truth for 226 functions (one memory-unsafe verdict, 0.4\%), coverage by library
(55--87\%), whether a realistic program can be written entirely from the bound
subset, and a comparison against four alternatives on the same sample and the
same scorer: a signature-only binding, a type-directed structural filter, an
operationalisation of the closest prior system, and two frontier language
models.
```

---

# FIX 4 — Introduction, contribution 3

**Find:** `\textbf{A hazard catalogue} (Table~\ref{tab:defects}): seventeen C API`

**Replace with:** `\textbf{A hazard catalogue} (Table~\ref{tab:defects}): twenty-two C API`

---

# FIX 5 — §III-A, the "every fact is evidenced" overstatement

**Find:**

```latex
The central artifact is a \emph{capability specification}: a per-function record
of the memory intent a signature cannot express. Every fact in it is
\emph{evidenced}, carrying not just a value but the analysis layer that produced
it, a confidence score in $[0,1]$ recording how strongly that layer's evidence
supports the value, and a flag recording whether the value has been confirmed
against the compiled library in the narrow case where that is possible:
```

**Replace with:**

```latex
The central artifact is a \emph{capability specification}: a per-function record
of the memory intent a signature cannot express. Each parameter's intent is
\emph{evidenced}, carrying not just a value but the analysis layer that produced
it, a confidence score in $[0,1]$ recording how strongly that layer's evidence
supports the value, and a flag recording whether the value has been confirmed
against the compiled library in the narrow case where that is possible. The
function-level facts (lifecycle, handle type, owner) carry their provenance in
the analysis report rather than in the record itself, which is a limitation we
note where it matters (\S\ref{sec:override}):
```

---

# FIX 6 — §III-C, the leak example

**Find:**

```latex
arises only when a genuine ownership-\emph{transfer} function is misclassified
as borrowed; \texttt{cJSON\_DetachItemFromObject} is one such case, where the
caller does take ownership of the detached node.
```

**Replace with:**

```latex
arises only when a genuine ownership-\emph{transfer} function is misclassified
as borrowed. SQLite's \texttt{sqlite3\_str\_new} is a case the vocabulary
itself cannot express: it returns a \texttt{sqlite3\_malloc64} result on the
success path and the address of a static sentinel when that allocation fails,
through a single \texttt{return} statement. No one value of \texttt{owner} is
correct for both paths, and the safe one leaks.
```

---

# FIX 7 — §IV-A, include paths

**Find:**

```latex
not adapted to any of them, and the only per-library work was supplying include
paths and, where a library's build generates configuration headers, running its
configure step so its source would parse. They were chosen to span handle idioms
```

**Replace with:**

```latex
not adapted to any of them, and the only per-library work was supplying include
paths and, where a library's build generates configuration headers, running its
configure step so its source would parse. That work is not as trivial as it
sounds, and \S\ref{sec:coverage-blind} reports what getting it wrong cost. They
were chosen to span handle idioms
```

**Then find:**

```latex
Two implementation-level fixes followed the first four of these runs,
a missing entry in the C type registry, and a type-match guard on lifecycle
forwarding, so those four figures are post-fix. libxml2 was run after the
implementation was frozen at a recorded commit and its figures are reported as
first obtained (\S\ref{sec:blind}).
```

**Replace with:**

```latex
Two implementation-level fixes followed the first four of these runs, a missing
entry in the C type registry and a type-match guard on lifecycle forwarding, so
those libraries were blind with respect to the design of the analysis rather
than to every line of its implementation. All figures reported here come from a
single frozen commit, re-run after those fixes and after the include-path audit
of \S\ref{sec:coverage-blind}; \S\ref{sec:blind} additionally reports libxml2
exactly as first obtained, before any of it.
```

---

# FIX 8 — Table II (calibration coverage)

**Find:**

```latex
Exported functions                  & 78 & 291 \\
\quad Dropped at extraction (variadic) & 0 & 8 \\
\quad Bound                         & 68 & 172 \\
\quad Refused                       & 10 & 111 \\
```

**Replace with:**

```latex
Exported functions                  & 78 & 291 \\
\quad Dropped at extraction (variadic) & 0 & 8 \\
\quad Absent from the compiled library & 0 & 12 \\
\quad Bound                         & 68 & 160 \\
\quad Refused                       & 10 & 111 \\
```

**And add to that table's caption**, after the existing text:

```latex
Twelve SQLite functions are declared in the header but compiled out of this
build (the \texttt{\_snapshot\_} family, column metadata, statement scan
status); a binding to an absent symbol is not a binding, so they are counted
apart from both the bound and the refused sets.
```

---

# FIX 9 — §IV-B, the Measures paragraph

**Find:**

```latex
\textbf{Measures.} We report five quantities, of which only the second is a
safety property: \emph{verdict accuracy}, the fraction where the ownership and
lifecycle verdicts both match the label, or where the analysis refused a
function the label also marks unsafe to expose; \emph{unsafe errors}, functions
bound with a verdict that permits an operation the label forbids; \emph{leak
errors}, functions bound with a conservative verdict that forgoes a legitimate
free; \emph{false refusals}, safe functions the fail-safe declined; and
\emph{benign disagreements}, verdicts that differ from the label without
permitting or forbidding any operation.
```

**Replace with:**

```latex
\textbf{Measures.} We report five quantities. \emph{Verdict accuracy} is the
fraction where the ownership and lifecycle verdicts both match the label, or
where the analysis refused a function the label also marks unsafe to expose.
\emph{Memory-unsafe errors} are functions bound with a verdict that permits an
operation corrupting memory: an \texttt{owner = caller} verdict where the
library retains ownership, or a \texttt{destroys} verdict on a function that
destroys nothing. \emph{Exposability disagreements} are functions bound that
the label marks unexposable but where no memory error follows; we separate
these because they are a coverage limitation rather than a safety failure, and
\S\ref{sec:rq0-expose} explains why. \emph{Leak errors} are functions bound
with a conservative verdict that forgoes a legitimate free. \emph{False
refusals} are safe functions the fail-safe declined.

Two of these are reported by draw rather than pooled. The sample was extended
partway through this work, and the earlier draw's ``refused'' stratum was taken
against a state of the tool in which 13 of its 30 refused functions are now
bound; a function drawn as refused and later bound cannot register as a false
refusal, so that draw structurally understates the rate. Accuracy and false
refusals are therefore given per draw, while the safety counts, which concern
bound functions, are pooled.
```

---

# FIX 10 — §IV-B, Results paragraph

**Find:**

```latex
\textbf{Results.} Table~\ref{tab:accuracy} reports them per library. Across 99
labelled functions drawn from the six libraries analyzed before the
implementation was frozen, 77 verdicts are correct. libxml2 is excluded from
this measurement: it was run after freezing (\S\ref{sec:blind}) and we did not
label it, so its 474 bindings contribute to the coverage figures but not to the
accuracy figures.
```

**Replace with:**

```latex
\textbf{Results.} Table~\ref{tab:accuracy} reports them per library across 226
labelled functions from all seven libraries. One verdict permits an operation
that corrupts memory, fifteen forgo a legitimate free, and five bind a function
the labels mark unexposable without any memory consequence.
Table~\ref{tab:draws} reports accuracy and false refusals for the two draws
separately.
```

---

# FIX 11 — Table III, replaced entirely

**Find** the whole `\begin{table}[t] ... \label{tab:accuracy} ... \end{table}`
block and **replace with:**

```latex
\begin{table}[t]
\caption{Accuracy against hand-labelled ground truth, stratified sample per
library, 226 functions. ``Mem.\ unsafe'' permits an operation that corrupts
memory; ``Expose'' binds a function the label marks unexposable with no memory
consequence (\S\ref{sec:rq0-expose}); ``Leak'' forgoes a legitimate free.
Figures are for the configuration with no manual annotations
(\S\ref{sec:override}).}
\label{tab:accuracy}
\centering
\footnotesize
\setlength{\tabcolsep}{3pt}
\begin{tabular}{lrrrrr}
\toprule
\textbf{Library} & \textbf{n} & \textbf{Mem.\ unsafe} & \textbf{Expose} & \textbf{Leak} & \textbf{False ref.} \\
\midrule
cJSON   & 32 & 0 & 1 & 1 & 8 \\
SQLite  & 40 & 0 & 0 & 2 & 5 \\
zlib    & 27 & 0 & 0 & 0 & 4 \\
libpng  & 31 & 0 & 0 & 0 & 6 \\
libpq   & 36 & 1 & 0 & 5 & 4 \\
libgit2 & 40 & 0 & 4 & 5 & 6 \\
libxml2 & 20 & 0 & 0 & 2 & 3 \\
\midrule
\textbf{Overall} & \textbf{226} & \textbf{1 (0.4\%)} & \textbf{5 (2.2\%)} & \textbf{15 (6.6\%)} & \textbf{36} \\
\bottomrule
\end{tabular}
\end{table}

\begin{table}[t]
\caption{Accuracy and false refusals by draw. The earlier draw's ``refused''
stratum was sampled against a state of the tool in which 13 of its 30 refused
functions are now bound, so it cannot register those as false refusals; the
extension was drawn against the frozen specification and is the figure to read.}
\label{tab:draws}
\centering
\footnotesize
\begin{tabular}{lrrr}
\toprule
\textbf{Draw} & \textbf{n} & \textbf{Verdict accuracy} & \textbf{False refusals} \\
\midrule
Original, stale strata & 99  & 81.8\% & 8 (8\%) \\
Extension, frozen specification & 127 & 53.5\% & 28 (22\%) \\
\bottomrule
\end{tabular}
\end{table}
```

> Re-run `04b` after the escape-store fix and correct the Correct/False-ref
> columns if they moved; the safety columns above are from `04f`.

---

# FIX 12 — §IV-B, benign / unsafe / leak paragraphs

**Find** the three paragraphs beginning `The six benign disagreements`,
`The single unsafe verdict is \texttt{cJSON\_InitHooks}`, and `The three leak
errors are all the same shape`, and **replace all three with:**

```latex
\textbf{The one memory-unsafe verdict} is \texttt{PQconnectPoll}, classified
\texttt{destroys} where the label says \texttt{uses}. It is the fourth instance
in this work of the failure mode \S\ref{sec:failsafe-scope} names as the one
decision that does not abstain: lifecycle classification asserts, and when
forwarding concludes that a function frees a handle the runtime releases it.
The other three, \texttt{sqlite3\_exec}, \texttt{PQexec} and libpng's read
family, were caught earlier and are pinned by regression tests; this one was
found by extending the ground-truth sample.

\textbf{The fifteen leaks} fall into three shapes rather than one.
Five are \texttt{char*} returns, where string ownership deliberately runs a
simpler rule set than pointer ownership: it has no escape rule and no transfer
rule, because a wrong deallocator call on a string is heap corruption rather
than a leak. Five are libpq functions that one manual annotation resolves
(\S\ref{sec:override}); Table~\ref{tab:accuracy} reports the un-annotated
configuration. The remainder are structural out-handles marked
\texttt{owner = library} where the label says \texttt{caller}, which is
ownership rule~5 functioning as designed: the handle is usable and cannot be
freed, so the worst outcome is a bounded leak rather than a double free.
```

---

# FIX 13 — new subsection after the leak paragraph

**Insert:**

```latex
\subsubsection{Exposability disagreements are not memory errors}
\label{sec:rq0-expose}

Five bound functions carry a label saying they should not be exposed at all,
and we report them apart from the memory-unsafe verdict because reading their
implementations shows no memory error follows. All five are initialiser
functions taking a struct whose members are function pointers:
\texttt{cJSON\_InitHooks}, and libgit2's \texttt{git\_remote\_init\_callbacks},
\texttt{git\_submodule\_update\_init\_options} and
\texttt{git\_worktree\_add\_init\_options}. Caller-allocated state analysis
(\S\ref{sec:pipeline}) admits the struct: the library never returns it, never
frees it, declares it itself, exposes an initialiser, and Clang can size it.
The binding therefore allocates a zeroed buffer and passes it in.

That is correct use in every case we examined. \texttt{cJSON\_InitHooks} tests
each member against \texttt{NULL} and falls back to \texttt{malloc} and
\texttt{free}; \texttt{git\_remote\_init\_callbacks} writes a template into the
struct and reads nothing from it. What the caller cannot then do is install a
callback, because a function pointer has no representation across a protocol
boundary. The binding is safe and useless, which is a coverage limitation of
the capability model rather than a failure of the fail-safe, and we count it as
such.
```

---

# FIX 14 — §IV-B, Precision paragraph

**Find** the paragraph beginning `\textbf{Precision of these estimates.} One
unsafe verdict in 99` and **replace with:**

```latex
\textbf{Precision of these estimates.} One memory-unsafe verdict in 226 gives a
Wilson 95\% interval of $[0.1\%, 2.5\%]$; the leak rate's interval is
$[4.1\%, 10.6\%]$. The upper bound on the memory-unsafe rate is the number to
weigh. It rests on a single function with an identified cause in a failure mode
the paper states does not abstain, rather than on a diffuse one; and the
comparison it should be read against is not zero but the alternatives of
\S\ref{sec:naive-baseline}, \S\ref{sec:ablation} and \S\ref{sec:llm}, measured
on this same sample with this same scorer.
```

---

# FIX 15 — Table VI (breadth)

**Find:**

```latex
zlib   & caller-allocated state   & 65/81   & 28  \\
libpng & return-handle + callback & 174/246 & 231 \\
libpq  & opaque context handle    & 43/165  & 42  \\
libgit2& reference-counted        & 680/834 & 723 \\
```

**Replace with:**

```latex
zlib   & caller-allocated state   & 62/81   & 28  \\
libpng & return-handle + callback & 173/246 & 231 \\
libpq  & opaque context handle    & 129/165 & 42  \\
libgit2& reference-counted        & 645/834 & 723 \\
```

---

# FIX 16 — Table VII (coverage across all seven)

**Find** the tabular body:

```latex
cJSON   & calibration & 78  & 68  & 87\% \\
SQLite  & calibration & 291 & 172 & 59\% \\
\midrule
zlib    & blind & 81  & 65  & 80\% \\
libpng  & blind & 246 & 174 & 71\% \\
libpq   & blind & 165 & 43  & 26\% \\
libgit2 & blind & 834 & 680 & 82\% \\
libxml2 & blind & 639 & 474 & 74\% \\
\midrule
\multicolumn{2}{l}{\textbf{Blind total}} & \textbf{1{,}965} & \textbf{1{,}436} & \textbf{73\%} \\
```

**Replace with:**

```latex
cJSON   & calibration & 78  & 68  & 87\% & 0 \\
SQLite  & calibration & 291 & 160 & 55\% & 0 \\
\midrule
zlib    & blind & 81  & 62  & 77\% & 0 \\
libpng  & blind & 246 & 173 & 70\% & 13 \\
libpq   & blind & 165 & 129 & 78\% & 6 \\
libgit2 & blind & 834 & 645 & 77\% & 0 \\
libxml2 & blind & 639 & 474 & 74\% & 7 \\
\midrule
\multicolumn{2}{l}{\textbf{Blind total}} & \textbf{1{,}965} & \textbf{1{,}483} & \textbf{75\%} & \\
```

**Change the column spec** `{llrrr}` to `{llrrrr}`, **the header row** to:

```latex
\textbf{Library} & \textbf{Role} & \textbf{Exported} & \textbf{Bound} & \textbf{Coverage} & \textbf{Files} \\
```

**and the caption** to:

```latex
\caption{Coverage across all seven libraries. ``Bound'' counts exported
functions present in the generated binding: a function that passes the policy
but has no symbol in the compiled library is not counted, and neither are the
31 allocator tools the binding synthesises for caller-allocated state. Variadic
functions are counted as refused. ``Files'' is the number of source files the
parse guard refused, all of them platform-specific or feature-gated after the
audit of \S\ref{sec:coverage-blind}.}
```

---

# FIX 17 — §IV-G, the libpq explanation (the important one)

**Find** the paragraph beginning `Table~\ref{tab:coverage-all} reports coverage
across all seven libraries. The aggregate over the blind set` through
`\ldots the clearest single improvement available to coverage.`

**Replace with:**

```latex
Table~\ref{tab:coverage-all} reports coverage across all seven libraries.
Across the five the analysis was never adapted to it sits between 70\% and
78\%, which is a narrower band than we expected and than an earlier version of
this work reported. That earlier spread was an artifact, and the way it arose
is worth reporting, because it is the same failure mode as the most transferable
finding of \S\ref{sec:rq1} and it hid for considerably longer.

libpq initially bound 43 of 165 functions, 26\%, and we attributed that to the
library's use of an incomplete struct declaration for \texttt{PGconn}. That
diagnosis was wrong. \texttt{fe-connect.c}, which defines every constructor and
destructor for \texttt{PGconn}, includes \texttt{pg\_config\_paths.h}, a header
PostgreSQL generates during its build and which we had not placed on the
include path. libclang emitted a fatal diagnostic, the truncation guard
correctly refused to analyze a file whose function bodies it could not trust,
and the type therefore never entered the handle set: not because its pointee
could not be resolved, which it could, but because no evidence about its
lifecycle survived. Supplying the directory takes libpq from 26\% to 78\% with
no change to the analysis. libgit2 carried a milder form of the same problem,
ten files requiring its vendored \texttt{xdiff}, \texttt{pcre} and
\texttt{ntlmclient} headers, costing four ownership verdicts rather than a
whole type.

The guard behaved correctly in both cases and said so in its report. What was
missing was any signal at the level a reader looks: a coverage figure alone
cannot distinguish a library whose conventions the analysis does not model from
one whose source it never read. We therefore report, for every library, how
many source files the guard refused, and we audited each: after the audit, the
26 refused files across all seven libraries are Windows-only, feature-gated
behind GSSAPI or OpenSSL, OS/400 platform code, or test programs, and none can
be supplied on this target. The general rule is the one \S\ref{sec:rq1} states
for a degraded parse, applied one level up: an analysis that silently declines
part of its input is indistinguishable from an analysis whose subject is
simpler than it is.
```

---

# FIX 18 — Table VIII (task coverage)

**Find:**

```latex
libpq   & 3/7 & \texttt{PQconnectdb} (unresolved pointee) \\
```

**Replace with:**

```latex
libpq   & complete (7/7) & --- (one annotation, \S\ref{sec:override}) \\
```

**And reorder** so libpq sits with the complete rows, and **amend the sentence
after the table:**

**Find:** `Table~\ref{tab:taskcov} reports the result. Two libraries can complete
their task entirely from the bound subset. The four that cannot are each blocked`

**Replace with:** `Table~\ref{tab:taskcov} reports the result. Three libraries
can complete their task entirely from the bound subset, libpq after the single
annotation of \S\ref{sec:override}. The three that cannot are each blocked`

---

# FIX 19 — §IV-H, libxml2 file count

**Find:** `Five variadic functions were refused at extraction. Eight source files
under \texttt{os400/} and \texttt{python/} failed to parse for missing platform
headers`

**Replace with:** `Five variadic functions were refused at extraction. Seven
source files, under \texttt{os400/} and \texttt{python/} and a \texttt{dlfcn}
shim, failed to parse for missing platform headers`

---

# FIX 20 — §V, the labels paragraph

**Find** the paragraph beginning `\textbf{The labels are ours.}` and **replace
with:**

```latex
\textbf{The labels are ours.} The ground truth is hand-labelled from
documentation and source. Where a library's documentation is silent on
ownership, the label reflects our reading of its implementation, the same
artifact Ferrule reads, so agreement there is weaker evidence than agreement on
a documented contract; we mark such labels in the artifact, and 115 of the 127
extension labels cite documentation rather than source alone.

\textbf{A stratified sample expires when the tool changes.} The strata of
\S\ref{sec:rq0} are defined partly by the tool's own behaviour, one of them
being the functions it refused. When the implementation changes, that stratum
no longer describes the same population: 13 of the 30 functions drawn as
refused in our first draw are bound in the frozen configuration, and none of
them can register as a false refusal. The effect is not small, 28 points of
verdict accuracy between the two draws (Table~\ref{tab:draws}), and it is
invisible unless the two are scored apart. We report them apart, and we note
the general point for anyone building a ground-truth sample against a moving
analysis: a sample stratified on a tool's output must be redrawn when the
output changes, or it silently measures the tool it was drawn against.
```

---

# FIX 21 — §V-D, the worklist numbers

**Find:**

```latex
Coverage on a library the analysis was not adapted to ranges from 26\% to 82\%,
so ``Ferrule refuses part of your API'' needs an answer rather than a defence.
```

**Replace with:**

```latex
Coverage on a library the analysis was not adapted to ranges from 70\% to 78\%,
so ``Ferrule refuses a fifth of your API'' needs an answer rather than a
defence.
```

**Then find:**

```latex
The effort scales with the number of distinct
\emph{reasons}, not the number of refused functions: on libpq, four reasons
against 122 refused functions.
```

**Replace with:**

```latex
The effort scales with the number of distinct \emph{reasons}, not the number of
refused functions. We tested this rather than asserting it. libpq's
\texttt{PGresult} is held borrowed for a principled reason: \texttt{PQgetResult}
passes the result and the connection to a user-registered event callback, and
whether that callback retains the result is user code no source analysis can
rule out. libpq's documentation says otherwise, and one manual fact recording
it resolves seven functions, not one: \texttt{PQgetResult} itself and the six
callers that reach it through \texttt{PQexecFinish}, which inherit the verdict
through the call-graph fixed point of \S\ref{sec:ownership}. The leverage is
therefore of two kinds, transitive over a type through handle propagation and
transitive over a call chain through ownership propagation, and the annotated
configuration completes libpq's task in Table~\ref{tab:taskcov}.

A manual fact is admitted before the ownership fixed point rather than patched
onto its output, which is what makes the second kind of leverage possible, and
it cannot override \texttt{check\_exposable}: an author may resolve what the
analysis abstained on, and may not make a callback or a writable buffer
exposable.
```

---

# FIX 22 — Conclusion

**Find:**

```latex
Measured against hand-labelled ground truth on a stratified sample
of 99 functions, the analysis is correct on 78\% of verdicts, with one error on
the unsafe side and three on the conservative side.
```

**Replace with:**

```latex
Measured against hand-labelled ground truth on a stratified sample of 226
functions, one verdict permits an operation that corrupts memory and fifteen
forgo a legitimate free, which is the asymmetry the design exists to produce.
```

---

# FIX 23 — insert the three drafted sections

- `section_IIE_llm_v2.tex`: replaces §II-E entirely; its second half becomes a
  new subsection after \S\ref{sec:naive-baseline}, labelled `sec:llm`.
- `section_ablation.tex`: new subsection labelled `sec:ablation` after the LLM
  one; also replaces the last two sentences of §II-D and the final paragraph of
  §V-C.

Check every `\label` against your file: the drafts assume `sec:rq0`,
`sec:failsafe`, `sec:ownership`, `sec:override`, `sec:pipeline`, `sec:t4`,
`tab:accuracy`.

---

# FIX 24 — five new hazard rows

**Insert before** `\hline` at the end of Table IV's body:

```latex
libpq & Generated header off the include path; guard refused the file defining every constructor & soundness & silent-empty & coverage audit \\
libxml2 & Escape traced through calls but not through direct member stores & memory safety & unsafe & extended ground truth \\
libxml2 & \texttt{NULL} assignment on an error path overwrote the real origin & soundness & conservative & \texttt{xmlDoRead} \\
several & Returned-value set collected argument names, not the returned value & coverage & conservative & cJSON detach family \\
libpq & Count parameter preceding its array; boundary regex missed camelCase & memory safety & unsafe & \texttt{PQsetResultAttrs} \\
```

**And update the caption:** `seventeen conventions` $\rightarrow$
`twenty-two conventions`, `(eight memory-safety)` $\rightarrow$
`(ten memory-safety)`, and `the last four rows` $\rightarrow$
`the last nine rows`.

---

# FIX 25 — final sweep

```bash
grep -n "26\\\\%\|1,436\|1{,}436\|78\\\\% correct\|seventeen\|99 functions" paper.tex
grep -n "held-out" paper.tex
grep -n "DetachItemFromObject" paper.tex
pdflatex paper.tex && pdflatex paper.tex
grep -c "Overfull" paper.log
```

Also confirm: the RQ2 bullet in §IV still says "the five libraries the analysis
was never adapted to" (correct); §IV-B's reference to
\S\ref{sec:naive-baseline} still resolves; and the 13-unsafe-to-expose count in
\S\ref{sec:naive-baseline} is recomputed for n=226 rather than left at the
n=99 value.