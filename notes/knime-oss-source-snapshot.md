# KNIME OSS Source Snapshot

This note records the local KNIME source-code snapshot cloned for repository mining.

## Clone Target

- Organization: `knime-oss`
- Source organization URL: https://github.com/knime-oss
- Local path: `/Users/vitaly/Home/git_proj/2026-06-knime-oss`
- Clone script: `scripts/clone_knime_oss_repos.sh`
- Clone command:

```bash
./scripts/clone_knime_oss_repos.sh /Users/vitaly/Home/git_proj/2026-06-knime-oss
```

## Clone Method

The script queries the GitHub REST API for all public repositories in the `knime-oss` organization and clones each repository with:

```bash
git clone --filter=blob:none
```

This keeps repository history available for mining while avoiding eager download of all historical blobs. During checkout, some repositories still downloaded large filtered or Git LFS-managed content.

## Result

- Repositories processed: 91
- Final cloned repository count: 91
- Final disk usage: 9.8G
- Clone status: completed

## Observed Warnings

The clone of `knime-r` completed with a non-fatal Git LFS warning:

```text
Encountered 4 files that should have been pointers, but weren't:
    org.knime.ext.r3.bin.win32.x86/R-Inst/library/RCurl/doc/withCookies.Rdb
    org.knime.ext.r3.bin.win32.x86/R-Inst/library/lme4/testdata/crabs_randdata00.Rda
    org.knime.ext.r3.bin.win32.x86/R-Inst/library/lme4/testdata/crabs_randdata2.Rda
    org.knime.ext.r3.bin.win32.x86/R-Inst/library/lme4/testdata/survdat_reduced.Rda
```

The script continued after this warning and completed all repositories.

## Notes For Data Mining

- Treat `/Users/vitaly/Home/git_proj/2026-06-knime-oss` as an external source snapshot, not as project source code.
- Do not commit the cloned repositories into this paper repository.
- Record future mining scripts, derived tables, and figures in this project repository.
- If the source snapshot is updated later, record the update date, command, repository count, disk usage, and any new warnings in this note or a dated successor note.
