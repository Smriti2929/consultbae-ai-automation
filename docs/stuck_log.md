# Stuck and Debugging Log

This log records implementation problems, evidence, and resolutions rather than
routine development activity.

## Entity-resolution ambiguity

Repeated names initially looked mergeable, but Arjun Mehta and Deepak Nair each
expanded to one-to-many candidates with conflicting email or phone evidence.
The resolution was to make valid exact normalized email/phone strong evidence,
keep name/city supporting-only, and return `AMBIGUOUS_REVIEW` when evidence is
name-only or strong identifiers conflict. Tests lock in the conflict behavior.

## Malformed source rows

Source 2 contains an entirely blank row and a shifted Isha Chopra row whose
values occupy the wrong columns. Source 3 contains an embedded header. Automatic
repair would require unsupported guesses, so all three are preserved as
`INVALID_SOURCE_RECORD` with their original JSON and explanations.

## Safe SQLite rebuilds and migrations

A deterministic rebuild is useful for ingestion but could erase later audio
submissions. Ingestion therefore builds and validates a temporary database,
atomically replaces the target, and refuses to rebuild once submissions exist.
Audio metadata columns are applied additively for older application databases.
Foreign-key enforcement and migration/data-preservation tests verify the result.

## FFmpeg and FFprobe on Windows

Metadata extraction failed clearly when executables were absent from `PATH`.
The setup now requires both commands to be verified after installation and the
terminal reopened after PATH changes. Subprocesses use argument arrays and
timeouts. Integration tests skip explicitly when the binaries are unavailable;
decoding and cleanup behavior remains unit-tested.

## Oversized uploads

Flask/Werkzeug can raise `RequestEntityTooLarge` before normal route validation.
The app sets a 25 MB `MAX_CONTENT_LENGTH` and handles that exception with a
friendly 413 page. Tests confirm the response exposes no traceback and creates
no file, person, or submission artifact.

## Audio-analysis rollback

A supported extension does not guarantee readable audio. The file is saved to
a unique temporary destination, analyzed before database writes, and removed on
metadata or database failure. Database writes use one transaction so a newly
created person cannot remain without its submission.

## n8n webhook modes and service reachability

The editor's test webhook is temporary and works only while listening; the
production webhook requires the workflow to be active/published. HTTP Request
failures also occur if Flask is not running or if `127.0.0.1` points to the n8n
container rather than the host. The workflow uses response-node mode, and both
IF branches terminate in their own **Respond to Webhook** node.

## Duplicate-check validation

Name-only lookup risked reintroducing the ambiguity deliberately avoided by the
ingestion pipeline. The API reuses the shared email/phone normalizers, rejects
requests without a valid strong identifier, performs SELECT-only canonical
lookups, and returns 409 rather than guessing when identifiers disagree.
