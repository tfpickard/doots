# Cross-Platform Theming Design

**Date:** 2026-07-25
**Branch:** `cyberdream-theme` (PR #5)
**Status:** Approved design, pending implementation plan

## Problem

The `cyberdream-theme` branch introduces a global theme system (`theme-set` plus
`.config/themes/<name>/`) that works on Linux and is broken on macOS. The branch
merges cleanly into `master` — it is 4 ahead / 0 behind, so the merge is a
fast-forward and GitHub reports `MERGEABLE`/`CLEAN`. Every defect below is a
runtime problem on macOS, not a merge conflict.

Four failures, verified on this machine (Darwin 27.0.0, `$HOME=/Users/tom`):

1. **Absolute Linux symlink committed to git.**
   `.config/themes/active -> /home/tom/doots/.config/themes/cyberdream` cannot
   resolve on macOS. Three further committed symlinks chain through it and
   therefore also dangle: `.config/ghostty/theme/active`, `.config/mako/config`,
   `.config/waybar/themes/dope/colors.css`.

2. **tmux is silently unthemed on macOS.** `~/.tmux.conf` is a live symlink into
   the repo, so this is current behavior. The branch deleted the hardcoded
   `SLEEZ_*` palette and replaced it with a guarded
   `if-shell '[ -e ~/.config/themes/active/tmux.conf ]'` source. That path does
   not exist on macOS, so the guard is false and tmux falls back to stock colors
   with no diagnostic.

3. **`theme-set` cannot run on macOS.** Line 19 uses `find -printf`, which is
   GNU-only; BSD `find` exits with `find: -printf: unknown primary or operator`,
   killing both `--list` and the fuzzel picker. Lines 60 and 120 use GNU `sed -i`
   semantics, which BSD `sed` rejects.

4. **The Makefile deploys none of it.** `CONFIG_DIRS` is
   `nvim hypr ghostty waybar dunst rofi alacritty`. The branch adds
   `.config/themes`, `.config/niri`, `.config/mako`, and `.config/scripts`, and
   leaves the Makefile unchanged, so `make symlinks` installs none of them — on
   either OS. It also deploys Wayland-only configs onto macOS.

A fifth issue is documented but deliberately out of scope; see Deferred Work.

## Goals

- `theme-set` runs correctly on stock macOS and stock Linux with no new
  dependencies.
- ghostty, tmux, bottom, and fastfetch are themed on both operating systems.
- Wayland-only applications (niri, waybar, mako, fuzzel, GTK) are skipped on
  macOS with a logged reason rather than failing.
- No machine-specific state is committed to git.
- Both operating systems are verified automatically on every pull request.

## Non-Goals

- macOS equivalents for the Wayland applications. There is no macOS analogue of
  niri or waybar, and substituting one is a different project.
- Restructuring how theme snippets are authored. The split between hand-written
  snippets and palette-derived configs is noted below but not changed here.
- Any change to theme colors or visual design.

## Platform Surface

Verified by probing this machine. Of the nine applications `theme-set` touches,
only two are currently installed on macOS.

| Application | macOS | Linux | Themed via |
|---|---|---|---|
| ghostty | installed | yes | symlink chain to `themes/active/ghostty` |
| tmux | installed | yes | `source-file` from `~/.tmux.conf` |
| bottom | installable | yes | `[colors]` block generated from `palette.json` |
| fastfetch | installable | yes | two ANSI values rewritten from `palette.json` |
| niri | impossible | yes | `// THEME:` marker lines patched in place |
| waybar | impossible | yes | CSS `@import` plus `SIGUSR2` reload |
| mako | impossible | yes | whole config is a symlink to `themes/active/mako.ini` |
| fuzzel | impossible | yes | `include=` directive (not currently wired) |
| GTK | impossible | yes | symlink to `gtk-4.0/gtk.css` (not currently wired) |

`bottom` and `fastfetch` are cross-platform but absent from this Mac *and*
absent from the repository. `fuzzel.ini` and `gtk.css` ship for all four themes
but have no consumer wired anywhere, making them orphans.

## Architecture: Capability-Driven Dispatch

`theme-set` carries a table of appliers. Each declares a probe command and a
target path, and runs only when both resolve; otherwise it logs a skip reason.
There are no `uname` checks anywhere in the script.

```
# applier   probe cmd    target                              apply fn
ghostty     ghostty      ~/.config/ghostty                   apply_ghostty
tmux        tmux         ~/.tmux.conf                        apply_tmux
bottom      btm          ~/.config/bottom/bottom.toml        apply_bottom
fastfetch   fastfetch    ~/.config/fastfetch/config.jsonc    apply_fastfetch
niri        niri         ~/.config/niri/config.kdl           apply_niri
waybar      waybar       ~/.config/waybar                    apply_waybar
mako        makoctl      ~/.config/mako                      apply_mako
fuzzel      fuzzel       ~/.config/fuzzel                    apply_fuzzel
gtk         -            ~/.config/gtk-4.0                   apply_gtk
```

Availability is discovered rather than declared, because "is this app themeable
here?" and "is this app installed here?" are the same question and one is
directly observable. macOS resolves to four appliers, a Wayland desktop to nine,
a headless Linux box to two — without any of them being a special case.

`--check` prints this table with resolved/skipped status and applies nothing. It
is the same data as the dispatch table, so the diagnostic cannot drift from the
behavior, and CI can assert the table directly.

## Design

### 1. Symlink topology and generated state

`themes/active` becomes per-machine generated state: gitignored, created by
`theme-set` and by `make theme`. This follows the precedent already set in
`.gitignore`, which treats `.config/ghostty/os/active` the same way.

| Path | Today | After |
|---|---|---|
| `.config/themes/active` | committed, absolute | gitignored, created relative |
| `.config/ghostty/theme/active` | committed, relative | unchanged |
| `.config/mako/config` | committed, relative | unchanged |
| `.config/waybar/themes/dope/colors.css` | committed, relative | unchanged |

The three consumer links are already relative and already correct. The absolute
link is the entire portability bug. `theme-set` creates the link relatively:

```sh
( cd "$THEMES_DIR" && ln -sfn "$theme" active )
```

The stored target becomes `cyberdream` rather than an absolute path, so it
carries no machine identity and means the right thing under both `/home/tom` and
`/Users/tom`.

Committing generated state is the root cause, not the path format. Even a
relative committed `active` would make every theme switch dirty the worktree,
so gitignoring it fixes a workflow problem as well as a portability one.

**Fresh-clone safety.** With `active` gitignored, a clone has three dangling
consumer links until a theme is selected. Handled by a new `make theme` target
that materializes `active` (defaulting to `cyberdream`), wired into `all` ahead
of `ghostty`. Consumers stay defensive regardless: ghostty's `?theme/active`
already tolerates absence, and tmux gains a committed default (§3).

`.gitignore` gains `.config/themes/active` directly beneath the existing
`os/active` entry, with a matching comment.

### 2. Portable shell

Two GNU-isms are replaced. Both have a subtlety that a naive rewrite would miss.

```sh
list_themes() {                    # replaces: find -printf (GNU-only)
    for d in "$THEMES_DIR"/*/; do
        d=${d%/}
        [ -L "$d" ] && continue    # `active` is a symlink-to-dir
        printf '%s\n' "${d##*/}"
    done | sort
}
```

The `[ -L ]` guard is required. `find -type d` silently excludes `active`
because find does not follow symlinks by default, but the glob `*/` *does* match
a symlink-to-directory. Without the guard, `active` appears as a selectable
theme — a regression that only surfaces after the first theme is set.

```sh
sed_inplace() {                    # replaces: sed -i (BSD/GNU syntax differ)
    _f=$1; shift
    _t=$(mktemp "$_f.XXXXXX") || return 1
    sed "$@" "$_f" >"$_t" && mv "$_t" "$_f"
}
```

The temp file is created in the target's directory rather than `$TMPDIR` so the
rename stays on one filesystem. A cross-filesystem `mv` degrades to copy plus
unlink, changing the inode and potentially clobbering permissions.

The remaining Linux-only commands (`niri msg`, `makoctl`, `pkill -USR2 waybar`,
`notify-send`, `fuzzel`) are reached only through appliers whose probes fail on
macOS, so they need no separate guarding.

### 3. Consumer fallbacks

tmux currently fails silently. It becomes a two-step with a committed default:

```tmux
if-shell '[ -e ~/.config/themes/active/tmux.conf ]' \
  'source-file ~/.config/themes/active/tmux.conf' \
  'source-file ~/.config/themes/default/tmux.conf'
```

`themes/default/` is a committed theme directory, so a fresh clone is styled
before `theme-set` has ever run. This converts the silent fallback into a
visible one without making it fatal.

### 4. Wire the orphans

Both are Linux-only and are skipped on macOS by the dispatch table. Each snippet
already exists for all four themes; only the consumer is missing.

- **fuzzel** — add `.config/fuzzel/fuzzel.ini` holding the non-color settings
  plus `include=../themes/active/fuzzel.ini`. The snippet header already
  documents this mechanism.
- **GTK** — commit `.config/gtk-4.0/gtk.css -> ../themes/active/gtk.css`. The
  snippet header already documents this target.

### 5. Ship bottom and fastfetch configs

Neither exists in the repository. `theme-set` patches `~/.config/bottom/bottom.toml`
and `~/.config/fastfetch/config.jsonc` in place — untracked, machine-local files
— so on macOS there is currently nothing for the applier to act on.

- Add `.config/bottom/bottom.toml` containing the
  `# >>> theme-set:colors` / `# <<< theme-set:colors` marker block the existing
  applier already expects.
- Add `.config/fastfetch/config.jsonc` containing the `"keys"` and `"title"`
  values the existing applier rewrites.
- Add `bottom` and `fastfetch` to `MAC_PACKAGES`, which currently still lists
  the archived `neofetch`. The branch already aliases `neofetch=fastfetch` in
  `.zshrc`.

### 6. Deploy

`CONFIG_DIRS` splits by platform so Wayland configs stop landing on macOS and
the branch's new directories start landing everywhere they should:

```make
COMMON_CONFIG_DIRS := nvim ghostty themes scripts bottom fastfetch
LINUX_CONFIG_DIRS  := hypr niri waybar mako fuzzel gtk-4.0 dunst
CONFIG_DIRS := $(COMMON_CONFIG_DIRS) \
               $(if $(filter Darwin,$(UNAME_S)),,$(LINUX_CONFIG_DIRS))
```

`alacritty` and `rofi` are dropped: both appear in today's `CONFIG_DIRS` but
neither directory exists in the repository, so `make symlinks` has been silently
skipping them. `dunst` and `hypr` do exist and are retained as Linux-only.

A new `make theme` target materializes `themes/active`:

```make
theme:
	@$(DOTFILES_DIR)/.config/themes/theme-set $(or $(THEME),cyberdream)
```

wired into `all` before `ghostty`.

### 7. Verification

`.github/workflows/theme.yml`, matrix over `ubuntu-latest` and `macos-latest`:

1. `shellcheck` the shell scripts under `.config/themes/` and `.config/scripts/`.
2. Assert no committed symlink has an absolute target — the regression that
   started this work:
   `git ls-tree -r HEAD | awk '$1=="120000"' | ... | grep '^/' && exit 1`
3. Run `theme-set --check` against a temp `$HOME` and assert it exits zero.
4. Run `theme-set <name>` for each theme, then assert every committed symlink
   resolves (`test -e`).

Step 4 is what makes the capability table meaningful: one script proves itself
on both runners rather than two code paths each exercised on only one. PR #5
currently has no status checks at all, so this is entirely new signal.

## Deferred Work

**Niri mutates a tracked file.** `theme-set` runs `sed -i` against
`.config/niri/config.kdl`, which is tracked in git. Switching theme on Linux
dirties the worktree, so the two machines' committed niri colors drift apart.
This is the same class of defect as the absolute symlink — generated state under
version control.

The clean fix is extracting the four `// THEME:` lines into a gitignored
`.config/niri/theme.kdl` include. It is deferred because niri's include support
must be verified on the Linux machine, and it has zero impact on macOS. It
should be filed as a separate issue.

**Snippet authoring is inconsistent.** Six snippets per theme are hand-written
(`ghostty`, `tmux.conf`, `mako.ini`, `fuzzel.ini`, `gtk.css`, `waybar.css`)
while niri, bottom, and fastfetch are generated from `palette.json` at apply
time. Adding a fifth theme therefore means hand-writing six files that could be
derived. Out of scope; noted for future consideration.

**`~/.config/ghostty` is a stale copy on this Mac.** It is a real directory, not
a symlink into the repo, so its contents have diverged (it still specifies
`theme = Rose Pine`, `cursor-invert-fg-bg`, and `shader/underwater`). This
predates the branch. `make ghostty` replaces it and also creates the currently
missing `os/active` symlink.

## Risks

- **Linux is unverified during implementation.** Development happens on macOS;
  the Linux appliers cannot be executed here. Mitigated by the CI matrix, which
  runs the real script on `ubuntu-latest`. Note that CI runners have neither
  niri nor waybar installed, so those appliers will be *skipped* rather than
  exercised — CI proves the dispatch and portability layers, not the Wayland
  apply functions themselves. Those still need a manual run on the Linux box.
- **`themes/default/` adds a fifth theme directory** that must stay in sync as a
  fallback. Kept minimal: tmux colors only, since that is the only consumer that
  needs a pre-`theme-set` default.
- **Gitignoring `active` changes the workflow.** After this change a fresh clone
  is unthemed until `make theme` or `theme-set` runs. Accepted deliberately, and
  the tmux default plus ghostty's optional include keep the degraded state
  usable.

## Success Criteria

1. `theme-set --list` and `theme-set <name>` succeed on both macOS and Linux.
2. `theme-set --check` reports four appliers on macOS and skips the Wayland five
   with reasons.
3. No committed symlink has an absolute target.
4. A fresh clone plus `make` yields a themed ghostty and tmux on both systems.
5. CI passes on `ubuntu-latest` and `macos-latest`.
6. Switching themes leaves the worktree clean, except for the deferred niri case.
