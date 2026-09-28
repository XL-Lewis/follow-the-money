# follow-the-money

Tracks gifts, hospitality, and financial interests disclosed by Australian politicians.

## Scope

- Members and Senators of the Australian Parliament
- Captures: gifts received, sponsored travel, shareholdings, real estate, directorships, trusts, liabilities, and the dated additions/deletions lodged against each statement

## Sources

| Chamber | Source | Format |
|---|---|---|
| House | [Register of Members' Interests](https://www.aph.gov.au/Senators_and_Members/Members/Register) | One PDF per member: the statement plus every alteration notice, parsed from the register's table template |
| Senate | JSON API behind the [Register of Senators' Interests](https://www.aph.gov.au/Parliamentary_Business/Committees/Senate/Senators_Interests/Senators_Interests_Register) | Structured statements and alterations |

The Senate API is undocumented; its base URL comes from the register page's `env.js`. A few House PDFs are scans rather than the template; they are kept and linked but not parsed.

## Usage

```sh
uv sync
uv run ftm fetch   # download new/changed documents into ./data
uv run ftm parse   # (re)derive declarations from the latest version of each
uv run ftm serve   # browse at http://127.0.0.1:5000
```

`--data-dir` changes the storage location. `fetch` is incremental: unchanged documents are skipped by ETag/Last-Modified or content hash.

## Status

Ingests all current House (151) and Senate (76) registers for the 48th Parliament.

## Stack

Python, SQLite, pdfplumber, Flask.
