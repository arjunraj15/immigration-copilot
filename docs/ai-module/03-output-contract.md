# Output contract and quote verification

## What the model returns

Every read prompt returns this JSON, enforced by structured outputs:

```json
{
  "category": "PASSPORT",
  "language": "en",
  "legible": true,
  "injection_flag": false,
  "fields": {
    "PASSPORT.Applicant": {"value": "Mira Dhawan", "quote": "Applicant: Mira Dhawan", "page": 1}
  }
}
```

`quote` is copied verbatim from the page text in its own language. `page` is the number from the page marker that holds the quote.

## What the module returns (`DocumentRead`)

In `backend/app/core/contracts.py`.

| Field | Meaning |
|---|---|
| `category` | The category the pages were read as |
| `language` | Language from the read, or the most common one from classify |
| `legible` | False when the read or all pages were illegible |
| `injection_flag` | True when any page of the whole upload was flagged |
| `fields` | Map of key to `ReadField` |
| `prompt_run_id` | The run row of the read call |
| `status` | `READ` or `REVIEW_REQUIRED` |

`ReadField` has `value`, `quote`, `page`, `verified` and `items`. For a scalar, `items` is null. See [array fields](04-array-fields.md) for the array shape. The old scalar shape did not change, and `quote`, `page` and `verified` now have defaults only so an array field can leave them empty.

## The quote verification rule

Code checks every quote against the extracted page text. It is the reader's job and happens after the model answers.

1. Normalise both sides. Unicode NFC, then collapse every run of whitespace to one space.
2. The quote must be a substring of the text of the page the field names.
3. An empty quote, a page that does not exist, or a quote found only on another page all mean `verified` is false.
4. An unverified field is kept, not dropped. The value, quote and page stay, and `verified` is false. Core must treat it as needing review.
5. Matching is case sensitive. The browser check in the test panel is case insensitive and is only a hint.

## Schema rules enforced at save time

`registry.validate_output_schema` rejects a schema when any field value object lacks `quote` or `page` in its properties or in its `required` list. The field keys in the schema must equal the keys in the field definitions. The generic prompt is the one exception, because its fields come from labels.

Schema keywords must be accepted by the Anthropic structured output API. Use plain `type`, `properties`, `required`, `items`, `enum` and `additionalProperties: false`. Do not use `minimum`, `maximum`, `minLength`, or an `additionalProperties` object.
