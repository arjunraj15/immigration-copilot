# Array fields

Use an array field when a document repeats the same kind of row, for example deductions on a pay statement, several pay lines or several stamps on a passport.

## Field definition

A definition with `type` set to `array` and an `items` list:

```json
{
  "key": "PAY_STATEMENT.Deductions",
  "label": "Deductions",
  "type": "array",
  "required": false,
  "hint": "One row per deduction line.",
  "items": [
    {"key": "Label", "label": "Deduction name", "type": "string", "required": true, "hint": null},
    {"key": "Amount", "label": "Amount", "type": "string", "required": true, "hint": null}
  ]
}
```

Rules, all checked by `registry.validate_field_definitions`:

1. `items` is required and non-empty for `array`, and is not allowed on any other type.
2. Item keys are unique inside the field. They are scalars only.
3. One level of nesting. An item cannot have type `array` or its own `items`.
4. Item keys `quote` and `page` are reserved because every row gets them.

## Output shape

```json
"PAY_STATEMENT.Deductions": {
  "value": [
    {"Label": "Tax", "Amount": "100.00", "quote": "Tax: 100.00", "page": 1},
    {"Label": "Health", "Amount": "50.00", "quote": "Health: 50.00", "page": 1}
  ]
}
```

The schema for the field is an object that requires `value`. `value` is an array of objects. Each object requires its item keys marked required plus `quote` and `page`. `validate_output_schema` rejects an item schema without `quote` or `page` declared and required, and rejects a nested array or object inside an item. The schema item keys must equal the definition item keys. Do not add `minItems`, so an empty array is valid.

## What the reader returns

`ReadField.items` is a list of `ReadItem`: `values` (item key to text), `quote`, `page`, `verified`. Each row is verified on its own with the normal quote rule. The field `verified` is true only when every row is verified, and an empty array is verified. A row with a bad quote stays in the list with `verified` false. Rows that are not objects are skipped. The field `value` is null and its own `quote` is empty.

Scalars next to arrays are unchanged. The generic read path is unchanged.

## Key lock

Array item keys are locked like field keys. Names are written `<field key>[].<item key>`. A new version cannot remove or rename one. Adding an item key is allowed.

## Prompt text

`format_field_definitions` adds a second line for an array field that tells the model to return a list with one object per row, each with its own quote and page. The passport seed prompt also has a rule for arrays.

## Seed proof

No sample pay statement shows deductions. Nothing in the typed sample documents repeats inside one document, except the two-page bundle in CASE-0026 where each page has its own `Applicant:` line. So `doc.read.passport` has an optional array `PASSPORT.Page Applicants` with item `Applicant`. In the pipeline the bundle is classified `UNKNOWN` and goes to the generic read, so this field rarely appears there. A live test forces it with a schema override to prove the API accepts the schema and that both rows verify.
