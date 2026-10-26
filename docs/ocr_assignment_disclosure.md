# OCR scan assignments: disclosure (OD-17), 2026-10-26

`tests/eval/assignments.jsonl` has a fixed seven-member line (PRD O.2) and a `reason` that must be null on a first line, so the
caveats below cannot sit in the assignment lines. They are recorded here, dated, and the lines are linked by document id.

| Id | Set | Kind |
|----|-----|------|
| S1 | tuning | scan (owner-supplied) |
| S2 | tuning | scan (owner-supplied), second tuning sample |
| S3 | held out | photograph of a computer monitor, balance sheet and profit and loss pages of one standalone annual report |

## Caveats on S3 (stated by the owner, recorded as given)

1. **Not a paper scan.** S3 is a phone photograph of a monitor showing the PDF. Its artefacts are screen glare and moire, not the
   skew and shadowing of a scanned paper page. A result on S3 says little about paper scans.
2. **Seen before assignment.** OD-17 says the assignment is made "before anyone inspects" the document. That was not met for S3. The
   owner saw the page while photographing it, and the other assistant that prepared the file looked at the rotated image to confirm it
   was upright and legible. No inspection by this project's code or by the assistant that builds it has taken place.

The owner chose to proceed with these limits. Neither caveat is hidden by the wording of the result: any S3 result must be reported
with both.
