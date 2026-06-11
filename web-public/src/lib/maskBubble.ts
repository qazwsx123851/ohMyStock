/**
 * Frontend defence-in-depth mask: replace any standalone 4-digit number
 * (TWSE/OTC stock codes are exactly 4 digits) with the masked token `STK-?`.
 *
 * Backend already strips real symbols via MaskedEventSerializer; this is the
 * second wall in case of regression. Intentionally narrow: only matches
 * exactly 4 ASCII digits flanked by word boundaries, so prices like `100`,
 * `12345`, or decimals like `0.72` are left alone.
 *
 * Spec: openspec/changes/web-public-pixel-office-mvp/specs/web-public-pixel-office/spec.md
 *       (Requirement: Frontend Mask Defense)
 */

const FOUR_DIGIT_RE = /\b\d{4}\b/g

export function stripFourDigit(input: string): string {
  return input.replace(FOUR_DIGIT_RE, 'STK-?')
}
